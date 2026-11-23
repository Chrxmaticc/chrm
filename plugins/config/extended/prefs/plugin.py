"""Preferences: the small switches the rest of the bot reads.

Everything here writes through :mod:`core.prefs` except the emoji overrides,
which live in ``settings.emojis`` and are read by ``bot.config.get_emoji``. The
disable list and cooldown are enforced in ``ChrmInstance.invoke``.
"""
from __future__ import annotations

import json
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from discord.ext import commands

from core import api, prefs

EMOJI_KEYS = ("success", "error", "loading", "tea", "image", "afk")


def _onoff(value: str):
    """``True`` / ``False`` for an on-off word, ``None`` when it is not one."""
    value = (value or "").strip().lower()
    if value in ("on", "true", "yes", "1"):
        return True
    if value in ("off", "false", "no", "0"):
        return False
    return None


class PrefsMixin:
    """Commands for this sub-cog; assembled into the package cog."""

    async def _save_prefs(self):
        await api.save_feature(self.bot, "prefs", prefs.raw(self.bot), tag="PREFS")

    async def _save_emojis(self):
        emojis = self.bot.config.data.setdefault("emojis", {})
        await api.patch_user(
            self.bot.user_id, {"settings": {"emojis": emojis}}, tag="EMOJIS"
        )

    # ------------------------------------------------------------ overview
    @commands.command(name="settings")
    async def settings(self, ctx):
        """what the engine is configured to do. usage: .settings"""
        settings = self.bot.config.data.get("settings", {})
        features = self.bot.config.data.get("features", {})
        delay = "off" if not settings.get("delays_enabled", True) else (
            f"{settings.get('delay_min', 1.5)}–{settings.get('delay_max', 4.5)}s"
        )
        afk = features.get("afk") if isinstance(features.get("afk"), dict) else {}
        levels = features.get("levels") if isinstance(features.get("levels"), dict) else {}
        friends = features.get("friends") if isinstance(features.get("friends"), dict) else {}
        wordle = features.get("wordle") if isinstance(features.get("wordle"), dict) else {}

        lines = [
            "### settings",
            "prefixes " + " ".join(f"`{item}`" for item in self.bot.config.get_prefixes()),
            f"human delay **{delay}** · command cooldown **{prefs.cooldown_seconds(self.bot):.0f}s**",
            f"timezone **{prefs.get(self.bot, 'timezone', 'UTC')}**",
            f"afk **{'on' if afk.get('enabled') else 'off'}** · "
            f"auto-replies **{len(features.get('autorespond') or {})}** · "
            f"auto-reactions **{len(features.get('autoreact') or {})}**",
            f"levels **{levels.get('xp', 0)} xp** · wordle **{wordle.get('played', 0)} played** · "
            f"friend alerts **{'on' if friends.get('notify') else 'off'}**",
            f"disabled commands **{len(prefs.disabled_names(self.bot))}** · "
            f"emoji overrides **{len(self.bot.config.data.get('emojis') or {})}**",
            "`.prefs` for game options · `.exportconfig` for a copy",
        ]
        await ctx.send("\n".join(lines))

    @commands.command(name="prefs")
    async def prefs(self, ctx):
        """the small preference switches. usage: .prefs"""
        await ctx.send(
            "### prefs\n"
            f"wordle hard mode **{'on' if prefs.get(self.bot, 'wordle_hard') else 'off'}**\n"
            f"wordle colorblind **{'on' if prefs.get(self.bot, 'wordle_colorblind') else 'off'}**\n"
            f"wordle spoilers **{'on' if prefs.get(self.bot, 'wordle_spoiler') else 'off'}**\n"
            f"timezone **{prefs.get(self.bot, 'timezone', 'UTC')}** · "
            f"cooldown **{prefs.cooldown_seconds(self.bot):.0f}s**\n"
            "`.wordlehard` · `.colorblind` · `.wordlespoiler` · `.timezone` · `.cooldown`"
        )

    # ------------------------------------------------------------ toggles
    async def _toggle(self, ctx, key: str, label: str, value: str):
        current = bool(prefs.get(self.bot, key))
        wanted = _onoff(value)
        if wanted is None and value.strip():
            return await ctx.warn(f"usage: `.{(ctx.command.name if ctx.command else key)} on|off`")
        if wanted is None:
            wanted = not current
        prefs.put(self.bot, key, wanted)
        await self._save_prefs()
        await ctx.approve(f"{label} **{'on' if wanted else 'off'}**.")

    @commands.command(name="wordlehard", aliases=["whard"])
    async def wordlehard(self, ctx, state: str = ""):
        """require revealed letters in later guesses. usage: .wordlehard on|off"""
        await self._toggle(ctx, "wordle_hard", "wordle hard mode", state)

    @commands.command(name="colorblind", aliases=["cb"])
    async def colorblind(self, ctx, state: str = ""):
        """swap green/yellow for blue/orange on wordle. usage: .colorblind on|off"""
        await self._toggle(ctx, "wordle_colorblind", "colorblind wordle", state)

    @commands.command(name="wordlespoiler", aliases=["wspoiler"])
    async def wordlespoiler(self, ctx, state: str = ""):
        """hide wordle boards behind spoiler tags. usage: .wordlespoiler on|off"""
        await self._toggle(ctx, "wordle_spoiler", "wordle spoilers", state)

    # ------------------------------------------------------------ timezone
    @commands.command(name="timezone", aliases=["tz"])
    async def timezone(self, ctx, *, zone: str = ""):
        """set or show the timezone used by `.time`. usage: .timezone Europe/London"""
        zone = zone.strip()
        if not zone:
            return await ctx.approve(f"timezone is **{prefs.get(self.bot, 'timezone', 'UTC')}**.")
        try:
            ZoneInfo(zone)
        except (ZoneInfoNotFoundError, ValueError):
            return await ctx.warn(f"unknown timezone `{zone}`. try `Europe/London` or `America/New_York`.")
        prefs.put(self.bot, "timezone", zone)
        await self._save_prefs()
        await ctx.approve(f"timezone set to **{zone}**.")

    # ------------------------------------------------------------ emojis
    @commands.command(name="setemoji")
    async def setemoji(self, ctx, key: str = "", emoji: str = ""):
        """override a feedback emoji. usage: .setemoji success ✅"""
        key = key.strip().lower()
        if key not in EMOJI_KEYS:
            return await ctx.warn("keys: " + ", ".join(f"`{name}`" for name in EMOJI_KEYS))
        if not emoji.strip():
            return await ctx.warn("usage: `.setemoji <key> <emoji>`")
        if len(emoji) > 60:
            return await ctx.warn("that is too long for an emoji.")
        self.bot.config.data.setdefault("emojis", {})[key] = emoji.strip()
        await self._save_emojis()
        await ctx.approve(f"**{key}** is now {emoji.strip()}")

    @commands.command(name="resetemoji")
    async def resetemoji(self, ctx):
        """drop every emoji override. usage: .resetemoji"""
        self.bot.config.data["emojis"] = {}
        await self._save_emojis()
        await ctx.approve("emoji overrides cleared.")

    # ------------------------------------------------------------ access
    @commands.command(name="disable")
    async def disable(self, ctx, *, name: str = ""):
        """disable a command until you enable it. usage: .disable purge"""
        name = name.strip().lstrip(".").lower()
        if not name:
            return await ctx.warn("usage: `.disable <command>`")
        if name in prefs.BYPASS:
            return await ctx.warn(f"`{name}` has to stay available.")
        if self.bot.get_command(name) is None:
            return await ctx.warn(f"no command called `{name}`.")
        disabled = prefs.disabled_names(self.bot)
        if name in disabled:
            return await ctx.warn(f"`{name}` is already disabled.")
        disabled.append(name)
        prefs.put(self.bot, "disabled", disabled)
        await self._save_prefs()
        await ctx.approve(f"`{name}` is disabled. `.enable {name}` to bring it back.")

    @commands.command(name="enable")
    async def enable(self, ctx, *, name: str = ""):
        """re-enable a disabled command. usage: .enable purge"""
        name = name.strip().lstrip(".").lower()
        disabled = prefs.disabled_names(self.bot)
        if name not in disabled:
            return await ctx.warn(f"`{name}` is not disabled.")
        disabled.remove(name)
        prefs.put(self.bot, "disabled", disabled)
        await self._save_prefs()
        await ctx.approve(f"`{name}` is back.")

    @commands.command(name="disabled")
    async def disabled(self, ctx):
        """the disabled list. usage: .disabled"""
        names = prefs.disabled_names(self.bot)
        if not names:
            return await ctx.approve("nothing is disabled.")
        await ctx.send("**disabled**\n" + " ".join(f"`{name}`" for name in names))

    @commands.command(name="cooldown")
    async def cooldown(self, ctx, seconds: str = ""):
        """minimum seconds between commands, 0 for none. usage: .cooldown 3"""
        if not seconds.strip():
            return await ctx.approve(f"command cooldown is **{prefs.cooldown_seconds(self.bot):.0f}s**.")
        try:
            value = max(0.0, min(60.0, float(seconds)))
        except ValueError:
            return await ctx.warn("usage: `.cooldown <seconds>` (0–60)")
        prefs.put(self.bot, "cooldown", value)
        await self._save_prefs()
        await ctx.approve(f"command cooldown set to **{value:.0f}s**.")

    # ------------------------------------------------------------ backup
    @commands.command(name="exportconfig")
    async def exportconfig(self, ctx):
        """copy of settings, emojis and prefs as json. usage: .exportconfig"""
        payload = {
            "settings": self.bot.config.data.get("settings", {}),
            "emojis": self.bot.config.data.get("emojis", {}),
            "prefs": prefs.raw(self.bot),
        }
        text = json.dumps(payload, indent=1, ensure_ascii=False)
        await ctx.send("```json\n" + text[:1850] + "\n```")

    @commands.command(name="resetprefs")
    async def resetprefs(self, ctx, confirm: str = ""):
        """reset prefs, disabled commands and cooldown. usage: .resetprefs confirm"""
        if confirm.strip().lower() != "confirm":
            return await ctx.warn(
                "this clears prefs, the disabled list and the cooldown. "
                "run `.resetprefs confirm` if you mean it."
            )
        prefs.reset(self.bot)
        await self._save_prefs()
        await ctx.approve("preferences reset to defaults.")
