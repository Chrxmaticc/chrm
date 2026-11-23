"""Levels: use chrm, earn XP, unlock commands, collect achievements.

Nothing here is a subscription or a paywall -- XP comes from running any command
(``COMMAND_XP``) and from simply being active in Discord (``MESSAGE_XP`` every
``MESSAGE_COOLDOWN`` seconds). Levels are cheap on purpose: one level is
``XP_PER_LEVEL`` XP, so roughly six commands.

The catalogue in :mod:`plugins.levels.catalog` is registered as real commands on
load. A command above your level still exists in ``bot.all_commands`` so it can
answer "unlocks at level 4" instead of vanishing into silence.

State lives in ``settings.features.levels`` (see :mod:`plugins.levels.xp`) and is
written back through :func:`core.api.save_feature`, which is the same PATCH the
other cogs use, so it survives redeploys without a database of its own.
"""
from __future__ import annotations

import asyncio
import inspect
import time
from datetime import datetime

from discord.ext import commands

from core import api
from plugins.levels import catalog, xp

#: longest single message we post
MESSAGE_LIMIT = 1900


def _event_loop():
    """The running loop.

    ``bot.loop`` is a sentinel until ``Client.login`` runs -- which is *after*
    ``setup_hook``, i.e. exactly when extensions are loaded -- so a cog has to ask
    asyncio instead.
    """
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.get_event_loop()


def chunk(text: str, limit: int = MESSAGE_LIMIT):
    """Split on newlines, then hard-split anything still too long."""
    lines, out, current = text.splitlines(), [], ""
    for line in lines:
        while len(line) > limit:
            if current:
                out.append(current)
                current = ""
            out.append(line[:limit])
            line = line[limit:]
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit:
            out.append(current)
            current = line
        else:
            current = candidate
    if current:
        out.append(current)
    return out or [text[:limit]]


class Levels(commands.Cog):
    """XP, unlockable commands and achievements."""

    def __init__(self, bot):
        self.bot = bot

        features = bot.config.data.setdefault("features", {})
        stored = features.get("levels")
        self.state = xp.normalise(stored)
        features["levels"] = self.state

        #: name -> Command, so a reload can take them back off the bot
        self._registered = {}
        #: author id -> last time passive XP was granted
        self._passive_at = {}
        self._timers = set()
        self._dirty = False

        self._register_commands()
        self.flush_task = _event_loop().create_task(self._flush_loop())

    # ------------------------------------------------------------ basics
    @property
    def level(self) -> int:
        return xp.level_for(self.state["xp"])

    @property
    def unlocked_count(self) -> int:
        return sum(1 for entry in catalog.UNLOCKS if entry.level <= self.level)

    @property
    def total(self) -> int:
        return len(catalog.UNLOCKS)

    def cog_unload(self):
        for name in list(self._registered):
            try:
                self.bot.remove_command(name)
            except Exception as exc:  # noqa: BLE001 - unload must never raise
                print(f"[levels] could not remove `{name}`: {exc}")
        self._registered.clear()

        if getattr(self, "flush_task", None):
            self.flush_task.cancel()
        for task in list(self._timers):
            task.cancel()
        self._timers.clear()

        # Last write, fire-and-forget: cog_unload cannot be awaited.
        try:
            _event_loop().create_task(self._flush())
        except Exception:  # noqa: BLE001 - event loop may already be closing
            pass

    # ------------------------------------------------------------ registration
    def _register_commands(self):
        for entry in catalog.UNLOCKS:
            if entry.name in self.bot.all_commands:
                print(f"[levels] skipping `{entry.name}`: that name is already taken")
                continue
            command = commands.Command(
                self._runner(entry), name=entry.name, help=entry.desc
            )
            try:
                self.bot.add_command(command)
            except Exception as exc:  # noqa: BLE001 - one bad name must not stop the rest
                print(f"[levels] could not register `{entry.name}`: {exc}")
                continue
            self._registered[entry.name] = command

    def _runner(self, entry):
        """One closure per command; ``entry`` is captured, not a parameter."""

        async def runner(ctx, *, arg=None):
            await self._run_unlock(ctx, entry, arg or "")

        runner.__name__ = f"level_{entry.name}"
        return runner

    async def _run_unlock(self, ctx, entry, arg: str):
        if self.level < entry.level:
            return await ctx.warn(
                f"`{entry.name}` unlocks at level **{entry.level}** "
                f"({catalog.TIERS[entry.level]}). you are level {self.level} — "
                f"{xp.xp_to_next(self.state['xp'])} xp to go."
            )
        try:
            result = entry.run(self, ctx, arg)
            if inspect.isawaitable(result):
                result = await result
        except Exception as exc:  # noqa: BLE001 - report, never traceback into silence
            print(f"[levels] `{entry.name}` failed: {type(exc).__name__}: {exc}")
            return await ctx.deny(f"`{entry.name}` broke: {exc}")

        if result is None:
            return None
        if isinstance(result, catalog.Usage):
            return await ctx.warn(str(result))
        for piece in chunk(str(result)):
            await ctx.send(piece)
        return None

    # ------------------------------------------------------------ timers
    def start_timer(self, seconds: int, note: str, channel, author):
        task = _event_loop().create_task(self._timer(seconds, note, channel, author))
        self._timers.add(task)
        task.add_done_callback(self._timers.discard)
        return task

    async def _timer(self, seconds, note, channel, author):
        try:
            await asyncio.sleep(seconds)
            mention = f"<@{getattr(author, 'id', '')}> " if getattr(author, "id", None) else ""
            await channel.send(f"⏱ {mention}**{catalog.pretty_duration(seconds)}** is up — {note}")
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - channel deleted, no permission, ...
            print(f"[levels] timer could not fire: {type(exc).__name__}: {exc}")

    # ------------------------------------------------------------ state
    def _sync(self):
        """Re-merge the state after the dashboard may have replaced the blob.

        ``Config.apply_blob`` updates ``features.levels`` *in place*, so checking
        whether the dict object changed is not enough: always fold the stored copy
        back in, and :func:`xp.merge` keeps XP/counters monotonic.
        """
        features = self.bot.config.data.setdefault("features", {})
        merged = xp.merge(self.state, features.get("levels"))
        features["levels"] = merged
        self.state = merged

    async def _flush(self) -> bool:
        self._sync()
        self._dirty = False
        ok = await api.save_feature(self.bot, "levels", self.state, tag="LEVELS")
        if not ok:
            self._dirty = True
        return ok

    async def _flush_loop(self):
        while True:
            await asyncio.sleep(xp.FLUSH_SECONDS)
            if self._dirty:
                await self._flush()

    # ------------------------------------------------------------ xp
    async def _award(self, amount: int, *, ctx=None, kind: str = "command", command: str = ""):
        self._sync()
        state, stats = self.state, self.state["stats"]
        before = xp.level_for(state["xp"])

        state["xp"] = int(state["xp"]) + int(amount)
        if kind == "command":
            stats["commands"] += 1
            if command:
                stats["used"][command] = stats["used"].get(command, 0) + 1
            hour = datetime.now().hour
            if 2 <= hour < 5:
                stats["night"] = True
            elif 5 <= hour < 8:
                stats["early"] = True
        else:
            stats["messages"] += 1

        xp.touch_day(state)
        after = xp.level_for(state["xp"])
        fresh = xp.evaluate(state)
        self._dirty = True

        if after > before or fresh:
            await self._announce(ctx, before, after, fresh)
            await self._flush()

    async def _announce(self, ctx, before: int, after: int, fresh):
        if ctx is None or not self.state.get("notify", xp.NOTIFY_DEFAULT):
            return
        lines = []
        if after > before:
            names = [f"`{entry.name}`" for entry in catalog.by_level(after)]
            shown = " ".join(names[:6]) + (" …" if len(names) > 6 else "")
            lines.append(
                f"⬆️ level **{after}** · {xp.title_for(after)} — "
                f"**{len(names)}** new commands: {shown}"
            )
        for entry in fresh:
            lines.append(f"🏆 **{entry[1]}** — {entry[3]} {entry[2]}")
        if not lines:
            return
        try:
            await ctx.send("\n".join(lines))
        except Exception as exc:  # noqa: BLE001 - deleted channel, missing perms
            print(f"[levels] could not announce: {type(exc).__name__}: {exc}")

    # ------------------------------------------------------------ listeners
    @commands.Cog.listener()
    async def on_command_completion(self, ctx):
        if ctx.command is None:
            return
        try:
            await self._award(
                xp.COMMAND_XP, ctx=ctx, kind="command", command=ctx.command.qualified_name
            )
        except Exception as exc:  # noqa: BLE001 - xp must never break a command
            print(f"[levels] award failed: {type(exc).__name__}: {exc}")

    @commands.Cog.listener()
    async def on_message(self, message):
        """Passive XP for just using Discord -- one grant per cooldown window."""
        if message.author != self.bot.user:
            return
        prefixes = tuple(self.bot.config.get_prefixes())
        content = (message.content or "").lstrip()
        if content and content.startswith(prefixes):
            return
        if not content and not message.attachments:
            return
        now = time.time()
        key = getattr(message.author, "id", 0)
        if now - self._passive_at.get(key, 0) < xp.MESSAGE_COOLDOWN:
            return
        self._passive_at[key] = now
        try:
            await self._award(xp.MESSAGE_XP, ctx=None, kind="message")
        except Exception as exc:  # noqa: BLE001
            print(f"[levels] passive xp failed: {type(exc).__name__}: {exc}")

    # ------------------------------------------------------------ commands
    @commands.command(name="levels", aliases=["level", "xp"])
    async def levels_command(self, ctx):
        """your level, xp bar, streak and what is next"""
        state = self.state
        total = int(state["xp"])
        level = xp.level_for(total)
        stats = state["stats"]
        done = len(xp.unlocked(state))

        lines = [
            f"### level {level} · {xp.title_for(level)}",
            f"`{xp.bar(total)}` **{xp.xp_into(total)}/{xp.xp_needed(total)}** xp",
        ]
        if level < xp.MAX_LEVEL:
            lines.append(
                f"**{xp.xp_to_next(total)}** xp to level {level + 1} "
                f"· next: {' '.join(f'`{entry.name}`' for entry in catalog.by_level(level + 1)[:6])}"
            )
        else:
            lines.append(f"max level · **{total:,}** total xp earned")

        lines.extend([
            f"**{self.unlocked_count}/{len(catalog.UNLOCKS)}** commands · "
            f"**{done}/{len(xp.ACHIEVEMENTS)}** achievements",
            f"streak **{xp.current_streak(state)}d** (best {stats['best_streak']}d) · "
            f"**{stats['commands']}** commands · **{stats['messages']}** messages",
            "`.cmds` for the ladder · `.achievements` for the trophy case",
        ])
        await ctx.send("\n".join(lines))

    @commands.command(name="cmds", aliases=["unlocks"])
    async def cmds_command(self, ctx, level: int = None):
        """what you have unlocked, and what is still locked"""
        if level is not None:
            levels = [max(1, min(level, xp.MAX_LEVEL))]
        else:
            levels = list(range(1, xp.MAX_LEVEL + 1))

        lines = []
        for tier in levels:
            entries = catalog.by_level(tier)
            marker = "✅" if tier <= self.level else "🔒"
            lines.append(
                f"{marker} **level {tier} · {catalog.TIERS[tier]}** · "
                f"{(tier - 1) * xp.XP_PER_LEVEL} xp · {len(entries)} commands"
            )
            lines.append(" ".join(f"`{entry.name}`" for entry in entries))
        lines.append(f"-# {len(catalog.UNLOCKS)} commands · you have {self.unlocked_count} unlocked")
        for piece in chunk("\n".join(lines)):
            await ctx.send(piece)

    @commands.command(name="achievements", aliases=["ach", "trophies"])
    async def achievements_command(self, ctx):
        """every achievement, earned or not"""
        earned = self.state["achievements"]
        lines = [f"### achievements · {len(earned)}/{len(xp.ACHIEVEMENTS)}"]
        for key, name, desc, emoji, _test in xp.ACHIEVEMENTS:
            mark = "✅" if key in earned else "🔒"
            lines.append(f"{mark} {emoji} **{name}** — {desc}")
        for piece in chunk("\n".join(lines)):
            await ctx.send(piece)

    @commands.command(name="levelnotify")
    async def levelnotify_command(self, ctx, state: str = ""):
        """turn level-up and achievement messages on or off"""
        value = state.strip().lower()
        if value in ("", "status"):
            current = "on" if self.state.get("notify", xp.NOTIFY_DEFAULT) else "off"
            return await ctx.approve(f"level-up messages are **{current}**.")
        if value not in ("on", "off", "true", "false", "yes", "no"):
            return await ctx.warn("usage: `.levelnotify on|off`")
        self.state["notify"] = value in ("on", "true", "yes")
        self._dirty = True
        await self._flush()
        await ctx.approve(f"level-up messages **{'on' if self.state['notify'] else 'off'}**.")


async def setup(bot):
    await bot.add_cog(Levels(bot))
