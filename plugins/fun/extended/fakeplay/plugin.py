"""``.fakeplay`` -- a game activity with real art, optional lines and progress.

Three things changed after the old scrape host died:

* the games come from Discord's own detectable catalogue (see
  :mod:`plugins.fun.extended.gamecatalog`), which carries each game's icon hash,
  so the art no longer depends on a per-game API call;
* aliases from that catalogue are matched too, so ``cs2`` finds Counter-Strike 2;
* the activity type, large image and small image can be overridden per call.

Anything after a pipe becomes the two lines under the game name, and a line that
is only a percentage becomes a bar (``fakeplay.formatting``).

Every failure path edits the "searching" message rather than returning early, and
the catalogue download has a hard timeout: a dead source used to leave the
command looking dead too, because the old code waited on the default five-minute
aiohttp timeout while the user stared at "searching...".
"""
import random
import re
from datetime import timedelta

import aiohttp
import discord
from discord.ext import commands
from discord.http import Route

from plugins.fun.extended import gamecatalog

from .formatting import apply_progress, progress_bar, short_duration

#: ``--listen`` etc. anywhere in the query picks another activity type
TYPE_RE = re.compile(r"\s*--(play|listen|watch|compete)\b", re.IGNORECASE)
TYPES = {
    "--play": (discord.ActivityType.playing, "playing"),
    "--listen": (discord.ActivityType.listening, "listening to"),
    "--watch": (discord.ActivityType.watching, "watching"),
    "--compete": (discord.ActivityType.competing, "competing in"),
}

#: ``icon=<url>`` / ``small=<url>`` override the art for one call
ICON_RE = re.compile(r"\s*(?:icon|image|large)=(\S+)", re.IGNORECASE)
SMALL_RE = re.compile(r"\s*small=(\S+)", re.IGNORECASE)

#: ``.fakeplay random`` picks one instead of searching
RANDOM_WORDS = {"random", "rng", "any"}

#: catalogue download/parse ceiling; a hung source must not hang the command
CATALOGUE_TIMEOUT = aiohttp.ClientTimeout(total=120)


class FakePlayMixin:
    """Commands for this sub-cog; assembled into the package cog."""

    async def get_games(self):
        """Discord's detectable-games catalogue, downloaded once per process."""
        if self.games_cache:
            return self.games_cache
        print("[fakeplay] downloading detectable games catalogue...")
        async with aiohttp.ClientSession(timeout=CATALOGUE_TIMEOUT) as session:
            games = await gamecatalog.load(
                session, getattr(self, "cache_url", gamecatalog.SOURCE)
            )
        self.games_cache = games
        print(f"[fakeplay] catalogue ready: {len(games):,} games")
        return games

    async def get_game_icon(self, game):
        """Icon URL for a catalogued game, cached, with the old API as fallback."""
        app_id = game.app_id
        if app_id in self.icon_cache:
            return self.icon_cache[app_id]

        icon = gamecatalog.icon_url(game)
        if not icon:
            for path in ("/applications/{application_id}/rpc", "/applications/{application_id}/public"):
                try:
                    data = await self.bot.http.request(
                        Route("GET", path, application_id=int(app_id))
                    )
                except Exception:
                    continue
                if data.get("icon"):
                    icon = gamecatalog.CDN_ICON.format(app_id=app_id, icon=data["icon"])
                    break

        self.icon_cache[app_id] = icon
        return icon

    @commands.command(name="fakeplay")
    async def fakeplay(self, ctx, *, game_query: str):
        """fakes a game activity.

        usage: .fakeplay <game> [| details | state | 52% [in 30m]]
               [--listen|--watch|--compete] [icon=<url>] [small=<url>]

        ``random`` picks a game, ``icon=``/``small=`` swap the art, and a
        percentage line becomes a bar (``52% in 30m`` also counts down).
        """
        loading = self.bot.config.get_emoji("loading")
        error = self.bot.config.get_emoji("error")

        msg = await ctx.send(f"{loading} searching for `{game_query.strip()}`...")
        try:
            await self._apply_fakeplay(msg, game_query)
        except Exception as exc:  # noqa: BLE001 - the user must always get a reason
            print(f"[fakeplay] failed for {game_query!r}: {type(exc).__name__}: {exc}")
            try:
                await msg.edit(content=f"{error} fakeplay failed: `{type(exc).__name__}: {exc}`")
            except Exception:
                pass

    async def _apply_fakeplay(self, msg, game_query):
        """Resolve the query and set the presence; reports into ``msg``."""
        error = self.bot.config.get_emoji("error")
        success = self.bot.config.get_emoji("success")

        raw = game_query.strip()

        # Flags are pulled out of the whole query so they can sit anywhere.
        activity_type, type_label = TYPES["--play"]
        found = TYPE_RE.search(raw)
        if found:
            activity_type, type_label = TYPES[f"--{found.group(1).lower()}"]
            raw = TYPE_RE.sub(" ", raw, count=1).strip()

        icon_override = None
        found = ICON_RE.search(raw)
        if found:
            icon_override = found.group(1)
            raw = ICON_RE.sub(" ", raw, count=1).strip()

        small_image = None
        found = SMALL_RE.search(raw)
        if found:
            small_image = found.group(1)
            raw = SMALL_RE.sub(" ", raw, count=1).strip()

        parts = [part.strip() for part in raw.split("|")]
        query = parts[0] or raw.strip()
        fields, percent, eta, problem = apply_progress(parts[1:4])
        if problem:
            return await msg.edit(content=f"{error} {problem}.")

        details = fields[0] if len(fields) > 0 and fields[0] else None
        state = fields[1] if len(fields) > 1 and fields[1] else None

        try:
            games = await self.get_games()
        except Exception as exc:  # noqa: BLE001 - show which source failed
            return await msg.edit(content=f"{error} game database download failed: `{exc}`")

        if not games:
            return await msg.edit(content=f"{error} the game database came back empty.")

        if query.lower() in RANDOM_WORDS:
            game = random.choice(games)
        else:
            game = gamecatalog.find(games, query)

        name = game.name if game else query
        icon = icon_override or (gamecatalog.icon_url(game) if game else None)
        if not icon and game:
            icon = await self.get_game_icon(game)

        assets = None
        if icon or small_image:
            assets = discord.ActivityAssets(
                large_image=icon,
                large_text=name if icon else None,
                small_image=small_image,
            )

        # `52% in 30m` gets an end timestamp, which is what makes the client
        # animate a bar instead of just counting up from the start.
        start = discord.utils.utcnow()
        stamps = discord.ActivityTimestamps(start=start)
        if eta:
            stamps = discord.ActivityTimestamps(start=start, end=start + timedelta(seconds=eta))

        self.bot.locked_presence = True
        activity = discord.Activity(
            type=activity_type,
            name=name,
            application_id=game.app_id if game else None,
            details=details,
            state=state,
            assets=assets,
            timestamps=stamps,
        )
        await self.bot.change_presence(activity=activity)

        note = "" if icon else " *(no icon found)*"
        if not game:
            note = " *(not in the catalogue, no icon)*"
        extra = f" · {progress_bar(percent)}" if percent is not None else ""
        if percent is not None and eta:
            extra += f" (ends in {short_duration(eta)})"
        await msg.edit(content=f"{success} now fake {type_label}: **{name}**{note}{extra}")

    @commands.command()
    async def stopfakeplay(self, ctx):
        """stops the fake game and unlocks the status rotator"""
        self.bot.locked_presence = False
        await self.bot.change_presence(activity=discord.CustomActivity(name="chrm on top"))
        success = self.bot.config.get_emoji("success")
        await ctx.send(f"{success} stopped fake play. rotator unlocked.")
