"""Backups, restores and the small account switches.

``.backup`` writes the whole settings blob to a JSON file and ``.restore`` puts
it back, so a wiped dashboard record or a fresh host is one attachment away.
Secrets are stripped on the way out: a backup is meant to travel.

The rest are switches the engine reads at runtime:

    autoread on|off     ack incoming direct messages instead of leaving them bold
    autodelete <secs>   command replies delete themselves after N seconds
    ghost on|off        appear offline without disconnecting
    ignorechannel       silence the account's command dispatch in one channel

``.ignorechannel`` writes ``prefs.ignored_channels``; the check lives in
``ChrmInstance.invoke`` next to the disable list, and the three commands that can
undo it are on ``prefs.CHANNEL_BYPASS`` so an ignored channel is never a trap.
"""
from __future__ import annotations

import asyncio
import io
import json

import discord
from discord.ext import commands

from core import api, prefs

#: keys that never leave the account, at any nesting depth
SECRET_HINTS = ("token", "secret", "password", "webhook", "api_key", "apikey", "cookie")

#: a backup bigger than this is an outage, not a configuration
MAX_BACKUP_BYTES = 7_000_000

#: ceiling for ``.autodelete``
MAX_AUTODELETE = 3600


def onoff(value: str):
    """``True`` / ``False`` for an on-off word, ``None`` when it is not one."""
    value = (value or "").strip().lower()
    if value in ("on", "true", "yes", "1"):
        return True
    if value in ("off", "false", "no", "0"):
        return False
    return None


def merge(target: dict, incoming: dict) -> dict:
    """Recursive merge (incoming wins), so a restore does not drop untouched keys."""
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            merge(target[key], value)
        else:
            target[key] = value
    return target


def scrub(value):
    """Drop anything that looks like a credential, recursively."""
    if isinstance(value, dict):
        return {
            key: scrub(item)
            for key, item in value.items()
            if not any(hint in str(key).lower() for hint in SECRET_HINTS)
        }
    if isinstance(value, list):
        return [scrub(item) for item in value]
    return value


class ToolkitMixin:
    """Commands for this sub-cog; assembled into the package cog."""

    # ---------------------------------------------------------------- helpers
    def _toolkit(self) -> dict:
        """The mutable ``features.toolkit`` record, created on first use."""
        features = self.bot.config.data.setdefault("features", {})
        state = features.get("toolkit")
        if not isinstance(state, dict):
            state = {}
            features["toolkit"] = state
        return state

    async def _save_toolkit(self):
        await api.save_feature(self.bot, "toolkit", self._toolkit(), tag="TOOLKIT")

    async def _switch(self, ctx, state: str, key: str, label: str, on_text: str, off_text: str):
        """Shared body of the on/off switches; ``None`` means "show the state"."""
        turn = onoff(state)
        if turn is None:
            current = "on" if self._toolkit().get(key) else "off"
            return await ctx.warn(f"{label} is **{current}** — `.{'ghost' if key == 'ghost' else key} on|off`")
        self._toolkit()[key] = turn
        await self._save_toolkit()
        await ctx.approve(on_text if turn else off_text)

    # ---------------------------------------------------------------- backup
    @commands.command(name="backup", aliases=["exportcfg"])
    async def backup(self, ctx):
        """your whole configuration as a json file."""
        data = self.bot.config.data
        payload = {
            "version": 1,
            "exported": discord.utils.utcnow().isoformat(),
            "settings": scrub(data.get("settings") or {}),
            "features": scrub(data.get("features") or {}),
            "emojis": data.get("emojis") or {},
        }
        raw = json.dumps(payload, indent=2, ensure_ascii=False, default=str).encode()
        if len(raw) > MAX_BACKUP_BYTES:
            return await ctx.deny("the configuration is too large to send as a file.")
        filename = f"chrm-backup-{discord.utils.utcnow().strftime('%Y%m%d-%H%M%S')}.json"
        await ctx.send(
            "### backup\n"
            f"-# settings **{len(payload['settings'])}** · features **{len(payload['features'])}** · "
            f"{len(raw) / 1024:.1f} KB · secrets stripped",
            file=discord.File(io.BytesIO(raw), filename=filename),
        )

    @commands.command(name="restore", aliases=["importcfg"])
    async def restore(self, ctx, *, args: str = ""):
        """load a backup file or url. usage: .restore confirm (with the file attached)"""
        tokens = (args or "").split()
        confirm = any(token.lower() in ("confirm", "yes") for token in tokens)
        url = next((token for token in tokens if token.startswith("http")), "")
        attachments = list(getattr(ctx.message, "attachments", []) or [])
        if not attachments and not url:
            return await ctx.warn(
                "attach the `.json` backup to the command message (or give a url), "
                "then run `.restore confirm`."
            )
        try:
            if attachments:
                raw = await attachments[0].read()
            else:
                async with api.session().get(url) as response:
                    if response.status != 200:
                        return await ctx.deny(f"could not download that backup (http {response.status}).")
                    raw = await response.read()
        except Exception as exc:  # noqa: BLE001
            return await ctx.deny(f"could not read the backup: {exc}")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:  # noqa: BLE001
            return await ctx.deny("that file is not json.")
        if not isinstance(payload, dict):
            return await ctx.deny("that backup is not a configuration object.")

        settings = payload.get("settings") if isinstance(payload.get("settings"), dict) else {}
        features = payload.get("features") if isinstance(payload.get("features"), dict) else {}
        if not settings and not features:
            return await ctx.deny("that backup has no settings or features in it.")

        if not confirm:
            lines = [
                "### restore — preview",
                f"settings **{len(settings)}** keys · features **{len(features)}**",
                "-# this overwrites matching keys, not the whole config",
                "-# add `confirm` to the command to apply it",
            ]
            return await ctx.send("\n".join(lines))

        if settings:
            merge(self.bot.config.data.setdefault("settings", {}), scrub(settings))
        if features:
            merge(self.bot.config.data.setdefault("features", {}), scrub(features))
        body = {}
        if settings:
            body["settings"] = self.bot.config.data["settings"]
        if features:
            body["features"] = self.bot.config.data["features"]
        ok = await api.patch_user(self.bot.user_id, {"settings": body}, tag="RESTORE")
        if ok:
            await ctx.approve(f"restored **{len(settings)}** settings and **{len(features)}** feature blocks.")
        else:
            await ctx.warn("restored locally, but the dashboard write failed — it may not survive a restart.")

    # --------------------------------------------------------------- switches
    @commands.command(name="ghost", aliases=["invisible"])
    async def ghost(self, ctx, state: str = ""):
        """appear offline without disconnecting. usage: .ghost on"""
        turn = onoff(state)
        if turn is None:
            current = "invisible" if self._toolkit().get("ghost") else "online"
            return await ctx.warn(f"status is **{current}** — `.ghost on|off`")
        status = discord.Status.invisible if turn else discord.Status.online
        try:
            await self.bot.change_presence(status=status, activity=getattr(self.bot, "activity", None))
        except Exception as exc:  # noqa: BLE001
            return await ctx.deny(f"discord refused the presence change: {exc}")
        self._toolkit()["ghost"] = turn
        await self._save_toolkit()
        await ctx.approve(f"status is now **{'invisible' if turn else 'online'}**")

    @commands.command(name="autoread", aliases=["ackdms"])
    async def autoread(self, ctx, state: str = ""):
        """mark incoming direct messages read automatically. usage: .autoread on"""
        await self._switch(
            ctx, state, "autoread", "autoread",
            "direct messages will be marked read as they arrive.",
            "direct messages stay unread until you open them.",
        )

    @commands.command(name="autodelete", aliases=["ad"])
    async def autodelete(self, ctx, seconds: str = ""):
        """delete command replies after N seconds. usage: .autodelete 30 | off"""
        token = (seconds or "").strip().lower()
        if token in ("", "off", "0", "false", "no"):
            if token == "":
                current = float(self._toolkit().get("autodelete") or 0)
                return await ctx.warn(
                    f"autodelete is **{'off' if not current else f'{current:.0f}s'}** — `.autodelete 30` or `.autodelete off`"
                )
            self._toolkit()["autodelete"] = 0
            await self._save_toolkit()
            return await ctx.approve("command replies will stay put.")
        try:
            wait = float(token)
        except ValueError:
            return await ctx.deny("give me a number of seconds, or `off`.")
        if wait < 1:
            return await ctx.deny("give me at least one second.")
        capped = wait > MAX_AUTODELETE
        self._toolkit()["autodelete"] = MAX_AUTODELETE if capped else wait
        await self._save_toolkit()
        text = f"command replies delete themselves after **{self._toolkit()['autodelete']:.0f}s**."
        if capped:
            text += f" (capped from {wait:.0f}s)"
        await ctx.approve(text)

    # -------------------------------------------------------------- channels
    def _channel_arg(self, ctx, query: str):
        query = (query or "").strip()
        if not query:
            return ctx.channel
        token = query.strip("<#>")
        getter = getattr(self.bot, "get_channel", None)
        if token.isdigit() and callable(getter):
            found = getter(int(token))
            if found is not None:
                return found
        if ctx.guild is not None:
            name = query.lstrip("#")
            for channel in list(getattr(ctx.guild, "channels", []) or []):
                if getattr(channel, "name", "") == name:
                    return channel
        return None

    def _ignored(self) -> list:
        return prefs.ignored_channels(self.bot)

    async def _save_ignored(self, ignored: list):
        prefs.put(self.bot, "ignored_channels", ignored)
        await api.save_feature(self.bot, "prefs", prefs.raw(self.bot), tag="PREFS")

    @commands.command(name="ignorechannel", aliases=["ignorech"])
    async def ignorechannel(self, ctx, *, query: str = ""):
        """stop running commands in one channel. usage: .ignorechannel #general"""
        channel = self._channel_arg(ctx, query)
        if channel is None:
            return await ctx.deny(f"no channel matching **{(query or '').strip()[:40]}**.")
        ignored = self._ignored()
        if channel.id in ignored:
            return await ctx.warn(f"**#{getattr(channel, 'name', channel.id)}** is already ignored.")
        ignored.append(channel.id)
        await self._save_ignored(ignored)
        await ctx.approve(
            f"commands are ignored in **#{getattr(channel, 'name', channel.id)}** — "
            "`.ignoredchannels` lists them, `.unignorechannel` undoes it."
        )

    @commands.command(name="unignorechannel", aliases=["unignorech"])
    async def unignorechannel(self, ctx, *, query: str = ""):
        """start listening to a channel again. usage: .unignorechannel #general | all"""
        if (query or "").strip().lower() == "all":
            if not self._ignored():
                return await ctx.warn("no channels are ignored.")
            prefs.put(self.bot, "ignored_channels", [])
            await api.save_feature(self.bot, "prefs", prefs.raw(self.bot), tag="PREFS")
            return await ctx.approve("every channel is listened to again.")
        channel = self._channel_arg(ctx, query)
        if channel is None:
            return await ctx.deny(f"no channel matching **{(query or '').strip()[:40]}**.")
        ignored = self._ignored()
        if channel.id not in ignored:
            return await ctx.warn(f"**#{getattr(channel, 'name', channel.id)}** was not ignored.")
        prefs.put(self.bot, "ignored_channels", [item for item in ignored if item != channel.id])
        await api.save_feature(self.bot, "prefs", prefs.raw(self.bot), tag="PREFS")
        await ctx.approve(f"**#{getattr(channel, 'name', channel.id)}** is listened to again.")

    @commands.command(name="ignoredchannels", aliases=["ignoredch"])
    async def ignoredchannels(self, ctx):
        """the channels where commands are ignored."""
        ignored = self._ignored()
        if not ignored:
            return await ctx.warn("no channels are ignored.")
        getter = getattr(self.bot, "get_channel", None)
        lines = ["### ignored channels", f"**{len(ignored)}** quiet"]
        for channel_id in ignored[:25]:
            channel = getter(channel_id) if callable(getter) else None
            name = f"#{channel.name}" if channel is not None else f"`{channel_id}`"
            lines.append(name)
        if len(ignored) > 25:
            lines.append(f"-# and {len(ignored) - 25} more")
        await ctx.send("\n".join(lines))

    # --------------------------------------------------------------- listeners
    async def on_message_toolkit(self, message):
        """Ack incoming DMs when ``.autoread`` is on. Called from the cog listener."""
        if not self._toolkit().get("autoread"):
            return
        if getattr(getattr(message, "author", None), "id", None) == self.bot.user_id:
            return
        if not isinstance(message.channel, (discord.DMChannel, discord.GroupChannel)):
            return
        try:
            await message.ack()
        except Exception:  # noqa: BLE001 - an unread dm is not worth a traceback
            pass

    async def on_command_completion(self, ctx):
        """Schedule self-deletion of the command and its replies when asked."""
        wait = float(self._toolkit().get("autodelete") or 0)
        if wait <= 0:
            return
        ids = [ctx.message.id]
        try:
            async for message in ctx.channel.history(limit=10):
                # snowflakes are ordered, so anything at or after the invocation
                # is part of this command's output
                if message.author.id == self.bot.user_id and message.id >= ctx.message.id:
                    ids.append(message.id)
        except Exception:  # noqa: BLE001
            pass
        asyncio.create_task(self._expire(ctx.channel, ids, wait))

    async def _expire(self, channel, ids, wait):
        await asyncio.sleep(wait)
        getter = getattr(channel, "get_partial_message", None)
        for message_id in ids:
            try:
                if callable(getter):
                    await getter(message_id).delete()
            except Exception:  # noqa: BLE001 - already gone, or no permission
                continue
