"""Reminders and a todo list -- the two things a self-bot is actually asked for.

Both live in ``features`` so they survive a redeploy: a timer that forgets itself
when the host restarts is worse than no timer. A 15-second loop is the only place
that sends, so ``.remind`` itself just writes state and answers instantly.

    .remind 10m call the bank     one-off, delivered in this channel
    .reminders                    what is pending, with relative times
    .unremind 3 | all             drop one, or every one
    .todo add buy milk            a list that stays put
    .todo / .todo done 2 / .todo clear confirm
"""
from __future__ import annotations

import re
import time

from discord.ext import commands, tasks

from core import api

#: cap the lists so a runaway loop cannot fill the settings blob
MAX_REMINDERS = 100
MAX_TODOS = 200
#: a reminder that is overdue by more than this is dropped instead of spammed
GRACE_SECONDS = 3600
#: how often due reminders are checked
CHECK_SECONDS = 15

UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
DURATION = re.compile(r"^(\d+)\s*([smhdw])$", re.IGNORECASE)


def parse_duration(tokens):
    """``["1h", "30m"]`` -> seconds, or ``None`` when nothing parsed."""
    total = 0
    used = 0
    for token in tokens:
        match = DURATION.match(token)
        if not match:
            break
        total += int(match.group(1)) * UNITS[match.group(2).lower()]
        used += 1
    return (total, used) if used else (None, 0)


def pretty_duration(seconds: int) -> str:
    seconds = max(1, int(seconds))
    for unit, size in (("w", 604800), ("d", 86400), ("h", 3600), ("m", 60)):
        if seconds >= size and seconds % size == 0:
            return f"{seconds // size}{unit}"
    if seconds < 60:
        return f"{seconds}s"
    minutes, rest = divmod(seconds, 60)
    return f"{minutes}m{rest}s" if rest else f"{minutes}m"


class RemindersMixin:
    """Commands for this sub-cog; assembled into the package cog."""

    # ------------------------------------------------------------ storage
    def _list(self, key: str) -> list:
        features = self.bot.config.data.setdefault("features", {})
        value = features.get(key)
        if not isinstance(value, list):
            value = []
            features[key] = value
        return value

    def _reminders(self) -> list:
        return self._list("reminders")

    def _todos(self) -> list:
        return self._list("todos")

    async def _save_list(self, key: str, tag: str = "REMIND"):
        await api.save_feature(self.bot, key, self._list(key), tag=tag)

    # ------------------------------------------------------------ remind
    @commands.command(name="remind", aliases=["reminder"])
    async def remind(self, ctx, *args):
        """remind me in 10m — usage: .remind 10m call the bank"""
        tokens = list(args or ())
        while tokens and tokens[0].lower() in ("in", "for", "after"):
            tokens.pop(0)
        seconds, used = parse_duration(tokens)
        if seconds is None:
            return await ctx.warn(
                "usage: `.remind 10m call the bank` (s, m, h, d, w — `1h30m` works too)"
            )
        note = " ".join(tokens[used:]).strip()
        if not note:
            return await ctx.warn("what should i remind you about?")
        if seconds < 5:
            return await ctx.warn("give it at least five seconds.")

        reminders = self._reminders()
        if len(reminders) >= MAX_REMINDERS:
            return await ctx.warn(f"you already have {MAX_REMINDERS} reminders — clear some first.")
        due = time.time() + seconds
        entry = {
            "id": int(max([item.get("id", 0) for item in reminders] or [0])) + 1,
            "channel_id": getattr(ctx.channel, "id", 0),
            "text": note[:400],
            "due": due,
            "created": time.time(),
        }
        reminders.append(entry)
        await self._save_list("reminders")
        await ctx.approve(
            f"i will remind you in **{pretty_duration(seconds)}** (<t:{int(due)}:R>) — `#{entry['id']}`."
        )

    @commands.command(name="reminders", aliases=["remindlist"])
    async def reminders(self, ctx):
        """what is pending. usage: .reminders"""
        pending = sorted(self._reminders(), key=lambda item: item.get("due", 0))
        if not pending:
            return await ctx.warn("nothing pending. `.remind 10m <text>` sets one.")
        lines = [f"### reminders · {len(pending)}"]
        for entry in pending[:25]:
            channel = getattr(self.bot, "get_channel", lambda _id: None)(entry.get("channel_id"))
            where = f"#{channel.name}" if channel is not None else "here"
            lines.append(
                f"`{entry['id']}` <t:{int(entry.get('due', 0))}:R> · {where} · "
                f"{str(entry.get('text', ''))[:60]}"
            )
        if len(pending) > 25:
            lines.append(f"-# and {len(pending) - 25} more")
        lines.append("-# `.unremind <id>` · `.unremind all`")
        await ctx.send("\n".join(lines))

    @commands.command(name="unremind", aliases=["delremind"])
    async def unremind(self, ctx, which: str = ""):
        """drop a reminder. usage: .unremind 3 | all"""
        token = (which or "").strip().lower()
        if not token:
            return await ctx.warn("usage: `.unremind <id>` or `.unremind all`")
        reminders = self._reminders()
        if token in ("all", "everything"):
            if not reminders:
                return await ctx.warn("nothing pending.")
            reminders.clear()
            await self._save_list("reminders")
            return await ctx.approve("every reminder dropped.")
        if not token.isdigit():
            return await ctx.warn("usage: `.unremind <id>` or `.unremind all`")
        target = int(token)
        kept = [item for item in reminders if item.get("id") != target]
        if len(kept) == len(reminders):
            return await ctx.warn(f"no reminder `{target}`.")
        self.bot.config.data["features"]["reminders"] = kept
        await self._save_list("reminders")
        await ctx.approve(f"reminder `{target}` dropped.")

    # ------------------------------------------------------------ todo
    @commands.command(name="todo", aliases=["todos"])
    async def todo(self, ctx, action: str = "", *, text: str = ""):
        """a list that stays put. usage: .todo add buy milk · .todo done 1 · .todo clear confirm"""
        verb = (action or "").strip().lower()
        todos = self._todos()

        if verb in ("", "list", "ls"):
            if not todos:
                return await ctx.warn("nothing on the list. `.todo add <text>`")
            lines = [f"### todo · {len([item for item in todos if not item.get('done')])} open"]
            for index, item in enumerate(todos, start=1):
                mark = "✅" if item.get("done") else "▫️"
                lines.append(f"{mark} `{index}` {item.get('text', '')[:80]}")
            lines.append("-# `.todo done <n>` · `.todo rm <n>` · `.todo clear confirm`")
            return await ctx.send("\n".join(lines))

        if verb in ("add", "new", "+"):
            value = (text or "").strip()
            if not value:
                return await ctx.warn("usage: `.todo add buy milk`")
            if len(todos) >= MAX_TODOS:
                return await ctx.warn(f"the list is full ({MAX_TODOS}).")
            todos.append({"text": value[:200], "done": False, "created": time.time()})
            await self._save_list("todos", tag="TODO")
            return await ctx.approve(f"added — **{len(todos)}** on the list.")

        if verb in ("done", "check", "✓"):
            index = self._todo_index(text)
            if index is None:
                return await ctx.warn("which one? `.todo done 2`")
            todos[index]["done"] = True
            await self._save_list("todos", tag="TODO")
            return await ctx.approve(f"checked off **{todos[index]['text'][:60]}**.")

        if verb in ("rm", "remove", "delete", "del"):
            index = self._todo_index(text)
            if index is None:
                return await ctx.warn("which one? `.todo rm 2`")
            removed = todos.pop(index)
            await self._save_list("todos", tag="TODO")
            return await ctx.approve(f"removed **{removed['text'][:60]}**.")

        if verb == "clear":
            if (text or "").strip().lower() != "confirm":
                return await ctx.warn(f"that clears {len(todos)} items. `.todo clear confirm`")
            todos.clear()
            await self._save_list("todos", tag="TODO")
            return await ctx.approve("list cleared.")

        return await ctx.warn(
            "usage: `.todo add <text>` · `.todo done <n>` · `.todo rm <n>` · `.todo clear confirm`"
        )

    @staticmethod
    def _todo_index(text):
        token = (text or "").strip().split(" ")[0]
        return int(token) - 1 if token.isdigit() and int(token) > 0 else None

    # ------------------------------------------------------------ loop
    @tasks.loop(seconds=CHECK_SECONDS)
    async def check_due(self):
        """Send every reminder that has come due. Nothing else sends."""
        is_ready = getattr(self.bot, "is_ready", lambda: True)
        try:
            if not is_ready():
                return
        except Exception:  # noqa: BLE001 - a half-closed client is not a reason to stop
            return

        reminders = self._reminders()
        if not reminders:
            return
        now = time.time()
        kept, changed = [], False
        for entry in reminders:
            if float(entry.get("due", 0)) > now:
                kept.append(entry)
                continue
            changed = True
            if now - float(entry.get("due", 0)) > GRACE_SECONDS:
                continue  # too stale to be useful; drop it silently
            try:
                channel = self.bot.get_channel(entry.get("channel_id"))
            except Exception:  # noqa: BLE001
                channel = None
            if channel is None:
                kept.append(entry)  # the channel may come back; keep trying
                continue
            try:
                await channel.send(f"⏰ <@{self.bot.user_id}> reminder: {entry.get('text', '')}")
            except Exception as exc:  # noqa: BLE001 - deleted channel, no perms
                print(f"[REMIND] could not deliver {entry.get('id')}: {type(exc).__name__}: {exc}")
        self.bot.config.data["features"]["reminders"] = kept
        if changed:
            await self._save_list("reminders")

    @check_due.before_loop
    async def before_reminders(self):
        wait = getattr(self.bot, "wait_until_ready", None)
        if callable(wait):
            await wait()
