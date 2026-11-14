import discord
from discord.ext import commands
import aiohttp

class FakePlay(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.search_url = "https://store.steampowered.com/api/storesearch/"
        self.appdetails_url = "https://store.steampowered.com/api/appdetails"
        self.games_cache = {}

    async def search_games(self, query: str, limit: int = 10):
        """searches the official Steam store api for games matching the query"""
        params = {
            "term": query,
            "l": "english",
            "cc": "us",
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(self.search_url, params=params) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"steam store search returned {resp.status}")
                data = await resp.json()

        results = []
        for item in data.get("items", [])[:limit]:
            app_id = item.get("id")
            name = item.get("name")
            if app_id is None or not name:
                continue
            results.append({
                "app_id": str(app_id),
                "name": name,
            })
        return results

    async def get_app_details(self, app_id: str):
        """fetches official app details (confirms it's a game and is available)"""
        if app_id in self.games_cache:
            return self.games_cache[app_id]

        params = {"appids": app_id, "l": "english", "cc": "us"}
        async with aiohttp.ClientSession() as session:
            async with session.get(self.appdetails_url, params=params) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()

        entry = data.get(app_id, {})
        if not entry.get("success"):
            return None

        info = entry.get("data", {})
        details = {
            "app_id": app_id,
            "name": info.get("name"),
            "type": info.get("type", ""),
        }
        self.games_cache[app_id] = details
        return details

    async def resolve_game(self, query: str):
        """finds the best matching game for a query via the steam api"""
        results = await self.search_games(query)
        if not results:
            return None

        lowered = query.lower().strip()

        # rank the results: exact name > name contains query > everything else
        def score(r):
            name = r["name"].lower()
            if name == lowered:
                return 0
            if name.startswith(lowered):
                return 1
            if lowered in name:
                return 2
            return 3

        results.sort(key=score)

        # walk results, confirming each via appdetails until we get a real game
        for r in results:
            details = await self.get_app_details(r["app_id"])
            if not details:
                continue
            # only accept actual games (skip dlc, soundtracks, software, etc.)
            if details.get("type") == "game" and details.get("name"):
                return details

        return None

    @commands.command()
    async def fakeplay(self, ctx, *, game_query: str):
        """fakes playing a game with its official steam icon. usage: .fakeplay roblox"""
        loading = self.bot.config.get_emoji("loading")
        msg = await ctx.send(f"{loading} searching steam for `{game_query}`...")

        try:
            matched_game = await self.resolve_game(game_query)
        except Exception as e:
            self.bot.locked_presence = False
            error = self.bot.config.get_emoji("error")
            return await msg.edit(content=f"{error} steam api error: `{e}`")

        self.bot.locked_presence = True

        if matched_game:
            name = matched_game["name"]
            app_id = matched_game["app_id"]
            # application_id MUST be an int: discord uses it to resolve the app's
            # icon. a string is ignored by the gateway, so no image shows up.
            activity = discord.Activity(
                type=discord.ActivityType.playing,
                name=name,
                application_id=int(app_id),
            )
            await self.bot.change_presence(activity=activity)
            success = self.bot.config.get_emoji("success")
            await msg.edit(content=f"{success} now fake playing: **{name}** `(app {app_id})`")
        else:
            # fallback if the game isn't found on steam
            activity = discord.Activity(
                type=discord.ActivityType.playing,
                name=game_query,
            )
            await self.bot.change_presence(activity=activity)
            success = self.bot.config.get_emoji("success")
            await msg.edit(content=f"{success} now fake playing: **{game_query}** *(no steam app found)*")

    @commands.command()
    async def stopfakeplay(self, ctx):
        """stops the fake game and unlocks the status rotator"""
        self.bot.locked_presence = False
        await self.bot.change_presence(activity=discord.CustomActivity(name="chrm on top"))
        success = self.bot.config.get_emoji("success")
        await ctx.send(f"{success} stopped fake play. rotator unlocked.")

async def setup(bot):
    await bot.add_cog(FakePlay(bot))
