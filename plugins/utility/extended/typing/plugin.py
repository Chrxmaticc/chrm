"""``.type``: hold the "is typing..." indicator without sending anything.

Discord clears a channel's typing state about ten seconds after the last refresh,
so a longer ``.type`` re-enters ``typing()`` every few seconds instead of firing
once and going quiet.
"""
import asyncio
import time

import discord
from discord.ext import commands

#: hard cap: nothing good happens after five minutes of fake typing
MAX_SECONDS = 300.0

#: how often the indicator is refreshed (discord expires it at ~10s)
REFRESH_SECONDS = 8.0


def parse_seconds(raw: str) -> float:
    """``"30"``, ``"45s"``, ``"2.5m"`` -> seconds. Raises ``ValueError``."""
    text = raw.strip().lower()
    if not text:
        raise ValueError("empty duration")
    multiplier = 1.0
    if text.endswith("s"):
        text = text[:-1]
    elif text.endswith("m"):
        text, multiplier = text[:-1], 60.0
    return float(text) * multiplier


class TypingMixin:
    """Commands for this sub-cog; assembled into the package cog."""

    @commands.command(name="type")
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def type_indicator(self, ctx, seconds: str = "10"):
        """holds the typing indicator. usage: .type 30 / .type 2m"""
        error = self.bot.config.get_emoji("error")

        try:
            duration = parse_seconds(seconds)
        except ValueError:
            return await ctx.send(f"{error} usage: `.type <seconds>` -- e.g. `.type 30` or `.type 2m`.")

        if duration <= 0:
            return await ctx.send(f"{error} duration has to be more than zero.")
        if duration > MAX_SECONDS:
            return await ctx.send(f"{error} max is 5 minutes of typing.")

        # the command itself is the only trace we would leave behind
        try:
            await ctx.message.delete()
        except Exception:  # noqa: BLE001 - deleting the trigger is best effort
            pass

        deadline = time.monotonic() + duration
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                async with ctx.typing():
                    await asyncio.sleep(min(REFRESH_SECONDS, remaining))
        except (discord.Forbidden, discord.NotFound, discord.HTTPException):
            # lost the channel mid-typing; there is nothing left to signal into
            pass
