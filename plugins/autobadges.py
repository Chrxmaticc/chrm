import discord
from discord.ext import commands, tasks
import aiohttp
import re
import asyncio

class AutoBadges(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.badge_task = None
        self.is_running = False

    @commands.command()
    async def autobadges(self, ctx):
        """triggers the game badge rotation"""
        if self.is_running:
            error = self.bot.config.get_emoji("error")
            return await ctx.send(f"{error} autobadges is already running. use `.stopbadges` to cancel.")

        loading = self.bot.config.get_emoji("loading")
        msg = await ctx.send(f"{loading} downloading game database...")

        # 1. fetch the javascript file
        url = "https://cdn.phaseworld.top/Discord/badge.txt"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        raise Exception("failed to reach url")
                    text = await resp.text()
        except Exception as e:
            error = self.bot.config.get_emoji("error")
            return await msg.edit(content=f"{error} download failed: {e}")

        # 2. extract all game application ids using regex
        # the file is structured like: ["Game Name","123456789012345678"]
        game_ids = re.findall(r'"(\d{17,20})"', text)
        
        if not game_ids:
            error = self.bot.config.get_emoji("error")
            return await msg.edit(content=f"{error} could not find any game ids in the file.")

        success = self.bot.config.get_emoji("success")
        await msg.edit(content=f"{success} found **{len(game_ids)}** games. starting rotation...")

        # 3. start the rotation in the background
        self.is_running = True
        self.badge_task = self.bot.loop.create_task(self.rotate_badges(game_ids, ctx.channel))

    async def rotate_badges(self, game_ids, channel):
        try:
            for i, game_id in enumerate(game_ids):
                if not self.is_running:
                    break

                # create a fake game activity using the application id
                # discord.py-self allows passing application_id directly
                activity = discord.Activity(
                    type=discord.ActivityType.playing,
                    application_id=game_id
                )
                
                try:
                    await self.bot.change_presence(activity=activity)
                except Exception as e:
                    print(f"failed to set presence for {game_id}: {e}")
                    # if we hit a rate limit, wait a bit longer
                    await asyncio.sleep(5)

                # wait 3 seconds before the next game (adjust if rate limited)
                await asyncio.sleep(3)

                # log progress every 50 games so you know it's working
                if (i + 1) % 50 == 0:
                    print(f"[autobadges] cycled through {i + 1}/{len(game_ids)} games...")

            # finished or stopped
            self.is_running = False
            if self.bot.is_ready():
                await self.bot.change_presence(activity=discord.CustomActivity(name="chrm on top"))
                
        except asyncio.CancelledError:
            self.is_running = False
        except Exception as e:
            print(f"[autobadges] error: {e}")
            self.is_running = False

    @commands.command()
    async def stopbadges(self, ctx):
        """stops the game rotation"""
        if self.badge_task and not self.badge_task.done():
            self.is_running = False
            self.badge_task.cancel()
            emoji = self.bot.config.get_emoji("success")
            await ctx.send(f"{emoji} autobadges rotation stopped.")
        else:
            error = self.bot.config.get_emoji("error")
            await ctx.send(f"{error} autobadges is not running.")

async def setup(bot):
    await bot.add_cog(AutoBadges(bot))
