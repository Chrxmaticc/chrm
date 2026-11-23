import discord
from discord.ext import commands
from discord.http import Route
import aiohttp
import re

class FakePlayMixin:
    """Commands for this sub-cog; assembled into the package cog."""
    async def get_games(self):
        """downloads the game list once and caches it in memory"""
        if self.games_cache:
            return self.games_cache

        async with aiohttp.ClientSession() as session:
            async with session.get(self.cache_url) as resp:
                text = await resp.text()
        
        # extract name and id
        matches = re.findall(r'\["(.*?)","(\d{17,20})"\]', text)
        self.games_cache = matches
        return matches

    async def get_game_icon(self, app_id):
        """resolve a game's icon URL from its application id, cached per game.

        Only the CDN form renders: ActivityAssets rewrites it to ``mp:app-icons/...``,
        which is the media-proxy key clients can actually draw. A bare name and
        application_id draws the generic controller instead.
        """
        if app_id in self.icon_cache:
            return self.icon_cache[app_id]

        icon = None
        for path in ("/applications/{application_id}/rpc", "/applications/{application_id}/public"):
            try:
                data = await self.bot.http.request(
                    Route("GET", path, application_id=int(app_id))
                )
            except Exception:
                continue
            if data.get("icon"):
                icon = f"https://cdn.discordapp.com/app-icons/{app_id}/{data['icon']}.png"
                break

        self.icon_cache[app_id] = icon
        return icon

    @commands.command()
    async def fakeplay(self, ctx, *, game_query: str):
        """fakes playing a game with its official icon. usage: .fakeplay roblox [| details | state]"""
        loading = self.bot.config.get_emoji("loading")
        msg = await ctx.send(f"{loading} searching for `{game_query}`...")

        # Anything after a pipe becomes the metadata lines under the game name,
        # same order as .rpc: name | details | state
        parts = [part.strip() for part in game_query.split("|")]
        query = parts[0] or game_query.strip()
        details = parts[1] if len(parts) > 1 and parts[1] else None
        state = parts[2] if len(parts) > 2 and parts[2] else None

        try:
            games = await self.get_games()
        except Exception as e:
            error = self.bot.config.get_emoji("error")
            return await msg.edit(content=f"{error} failed to download game database.")

        matched_game = None
        # search for a close match
        for name, app_id in games:
            if query.lower() in name.lower():
                matched_game = (name, app_id)
                break

        self.bot.locked_presence = True

        if matched_game:
            name, app_id = matched_game
            icon = await self.get_game_icon(app_id)
            activity = discord.Activity(
                type=discord.ActivityType.playing,
                name=name,
                application_id=app_id,
                details=details,
                state=state,
                assets=discord.ActivityAssets(large_image=icon, large_text=name) if icon else None,
                timestamps=discord.ActivityTimestamps(start=discord.utils.utcnow()),
            )
            await self.bot.change_presence(activity=activity)
            success = self.bot.config.get_emoji("success")
            note = "" if icon else " *(no official icon found)*"
            await msg.edit(content=f"{success} now fake playing: **{name}**{note}")
        else:
            # fallback if the game isn't in the database
            activity = discord.Activity(
                type=discord.ActivityType.playing,
                name=query,
                details=details,
                state=state,
                timestamps=discord.ActivityTimestamps(start=discord.utils.utcnow()),
            )
            await self.bot.change_presence(activity=activity)
            success = self.bot.config.get_emoji("success")
            await msg.edit(content=f"{success} now fake playing: **{query}** *(no official icon found)*")

    @commands.command()
    async def stopfakeplay(self, ctx):
        """stops the fake game and unlocks the status rotator"""
        self.bot.locked_presence = False
        await self.bot.change_presence(activity=discord.CustomActivity(name="chrm on top"))
        success = self.bot.config.get_emoji("success")
        await ctx.send(f"{success} stopped fake play. rotator unlocked.")
