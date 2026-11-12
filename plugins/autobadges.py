import discord
from discord.ext import commands
import aiohttp
import re
import asyncio
import random

class AutoBadges(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.badge_task = None
        self.is_running = False

    @commands.command()
    async def testrpc(self, ctx):
        """tests if the bot can change your presence at all"""
        await ctx.send("testing rpc...")
        print("[debug] testing rpc")
        try:
            await self.bot.change_presence(activity=discord.Game(name="chrm test"))
            print("[debug] rpc test successful")
            await ctx.send("rpc test successful. check your profile.")
        except Exception as e:
            print(f"[debug] rpc test failed: {e}")
            await ctx.send(f"rpc test failed: {e}")

    @commands.command()
    async def autobadges(self, ctx, amount: int = 100, game_time: int = 5):
        """spoofs playing games. usage: .autobadges <amount> <seconds_per_game>"""
        if self.is_running:
            error = self.bot.config.get_emoji("error")
            return await ctx.send(f"{error} autobadges is already running. use `.stopbadges` to cancel.")

        loading = self.bot.config.get_emoji("loading")
        msg = await ctx.send(f"{loading} downloading game database...")

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

        # THIS IS THE FIX: Grab BOTH the name and the ID
        # The file looks like: ["Game Name","123456789012345678"]
        matches = re.findall(r'\["(.*?)","(\d{17,20})"\]', text)
        
        if not matches:
            error = self.bot.config.get_emoji("error")
            return await msg.edit(content=f"{error} could not parse the file format.")

        random.shuffle(matches)
        target_games = matches[:amount]

        total_seconds = len(target_games) * game_time
        total_minutes = total_seconds // 60

        success = self.bot.config.get_emoji("success")
        await msg.edit(content=f"{success} starting rotation for **{len(target_games)}** games (~{total_minutes}m total).")

        self.is_running = True
        self.badge_task = self.bot.loop.create_task(self.rotate_badges(target_games, game_time, msg))

    async def rotate_badges(self, games, game_time, status_msg):
        try:
            count = 0
            for game_name, game_id in games:
                if not self.is_running:
                    break

                # Send BOTH name and application_id
                activity = discord.Activity(
                    type=discord.ActivityType.playing,
                    name=game_name,
                    application_id=game_id
                )
                
                try:
                    await self.bot.change_presence(activity=activity)
                    print(f"[autobadges] set presence to {game_name} ({game_id})")
                except Exception as e:
                    print(f"failed to set presence for {game_name}: {e}")
                    await asyncio.sleep(10)

                await asyncio.sleep(game_time)
                
                count += 1
                if count % 10 == 0:
                    await status_msg.edit(content=f"playing game {count}/{len(games)} (current: {game_name})...")

            self.is_running = False
            if self.bot.is_ready():
                await self.bot.change_presence(activity=discord.CustomActivity(name="chrm on top"))
                success = self.bot.config.get_emoji("success")
                await status_msg.edit(content=f"{success} finished rotating {count} games.")
                
        except asyncio.CancelledError:
            self.is_running = False
        except Exception as e:
            print(f"[autobadges] error: {e}")
            self.is_running = False

    @commands.command()
    async def stopbadges(self, ctx):
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
