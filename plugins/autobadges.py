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
    async def autobadges(self, ctx, amount: int = 100, game_time: int = 5):
        """spoofs playing games. usage: .autobadges <amount> <seconds_per_game>"""
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
        game_ids = re.findall(r'"(\d{17,20})"', text)
        
        if not game_ids:
            error = self.bot.config.get_emoji("error")
            return await msg.edit(content=f"{error} could not find any game ids in the file.")

        # 3. randomize and slice to the requested amount
        random.shuffle(game_ids)
        target_games = game_ids[:amount]

        # calculate total time for the status message
        total_seconds = len(target_games) * game_time
        total_minutes = total_seconds // 60
        total_hours = total_minutes // 60

        time_str = f"{game_time}s"
        if total_hours > 0:
            time_str = f"{total_hours}h"
        elif total_minutes > 0:
            time_str = f"{total_minutes}m"

        success = self.bot.config.get_emoji("success")
        await msg.edit(content=f"{success} starting rotation for **{len(target_games)}** games ({time_str} total).")

        # 4. start the rotation in the background
        self.is_running = True
        self.badge_task = self.bot.loop.create_task(self.rotate_badges(target_games, game_time, msg))

    async def rotate_badges(self, game_ids, game_time, status_msg):
        try:
            count = 0
            for game_id in game_ids:
                if not self.is_running:
                    break

                # create a fake game activity using the application id
                activity = discord.Activity(
                    type=discord.ActivityType.playing,
                    application_id=game_id
                )
                
                try:
                    await self.bot.change_presence(activity=activity)
                except Exception as e:
                    print(f"failed to set presence for {game_id}: {e}")
                    await asyncio.sleep(10) # Back off if rate limited

                # wait the custom amount of time
                await asyncio.sleep(game_time)
                
                count += 1
                
                # update the message every 5 games (so we don't spam the chat)
                if count % 5 == 0:
                    await status_msg.edit(content=f"playing game {count}/{len(game_ids)} (current wait: {game_time}s)...")

            # finished
            self.is_running = False
            if self.bot.is_ready():
                await self.bot.change_presence(activity=discord.CustomActivity(name="chrm on top"))
                success = self.bot.config.get_emoji("success")
                await status_msg.edit(content=f"{success} finished rotating {count} games. check your profile in a bit!")
                
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
