import discord
from discord.ext import commands
from datetime import datetime
import asyncio
import re

class Presence(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.custom_rotator_task = None

    def cog_unload(self):
        if self.custom_rotator_task and not self.custom_rotator_task.done():
            self.custom_rotator_task.cancel()

    @commands.command()
    async def rpc(self, ctx, activity_type: str, *, args):
        """
        advanced rpc. attach an image to the command to use it!
        usage: .rpc playing name | details | state | large_img_url | small_img_url | elapsed
        """
        activity_type = activity_type.lower()
        parts = [p.strip() for p in args.split("|")]
        name = parts[0] if len(parts) > 0 else "chrm"

        error_emoji = self.bot.config.get_emoji("error")
        success_emoji = self.bot.config.get_emoji("success")

        # Handle Elapsed Timer
        timestamps = None
        if len(parts) > 0 and parts[-1].lower() == "elapsed":
            timestamps = {"start": int(datetime.now().timestamp())}
            parts.pop() # Remove 'elapsed' so it doesn't mess up image parsing

        # Check for attached files (camera roll/image uploads)
        large_img = None
        if ctx.message.attachments:
            large_img = ctx.message.attachments[0].url
        elif len(parts) > 3 and parts[3]:
            large_img = parts[3]

        # Streaming Handler
        if activity_type in ["streaming", "stream"]:
            if len(parts) < 2:
                return await ctx.send(f"{error_emoji} streaming requires a url. usage: `.rpc streaming title | url`")
            url = parts[1]
            try:
                self.bot.locked_presence = True
                await self.bot.change_presence(activity=discord.Streaming(name=name, url=url))
                await ctx.send(f"{success_emoji} now streaming: **{name}** at {url}")
            except Exception as e:
                await ctx.send(f"{error_emoji} error: {e}")
            return

        # Standard RPC Handler
        types = {
            "playing": discord.ActivityType.playing,
            "watching": discord.ActivityType.watching,
            "listening": discord.ActivityType.listening,
            "competing": discord.ActivityType.competing
        }
        
        if activity_type not in types:
            return await ctx.send(f"{error_emoji} invalid type. use playing, watching, listening, competing, or streaming.")

        details = parts[1] if len(parts) > 1 and parts[1] else None
        state = parts[2] if len(parts) > 2 and parts[2] else None
        small_img = parts[4] if len(parts) > 4 and parts[4] else None

        # Build assets
        assets = {}
        if large_img:
            assets["large_image"] = large_img
            if details:
                assets["large_text"] = details
        if small_img:
            assets["small_image"] = small_img
            if state:
                assets["small_text"] = state

        try:
            self.bot.locked_presence = True
            await self.bot.change_presence(activity=discord.Activity(
                type=types[activity_type],
                name=name,
                details=details,
                state=state,
                assets=assets if assets else None,
                timestamps=timestamps
            ))
            await ctx.send(f"{success_emoji} rpc updated: {activity_type} **{name}**")
        except Exception as e:
            await ctx.send(f"{error_emoji} error: {e}")

    @commands.command()
    async def customstatus(self, ctx, *, text):
        """sets a custom text status"""
        self.bot.locked_presence = True
        await self.bot.change_presence(activity=discord.CustomActivity(name=text))
        emoji = self.bot.config.get_emoji("success")
        await ctx.send(f"{emoji} custom status set to: {text}")

    @commands.command()
    async def clearstatus(self, ctx):
        """forcefully wipes the active rpc and stops any rotator"""
        self.bot.locked_presence = False
        
        # Stop the custom rotator if it's running
        if self.custom_rotator_task and not self.custom_rotator_task.done():
            self.custom_rotator_task.cancel()
            
        await self.bot.change_presence(activity=None)
        emoji = self.bot.config.get_emoji("success")
        await ctx.send(f"{emoji} presence completely wiped.")

    # ==========================================
    # MANUAL STATUS ROTATOR (Only runs if they ask)
    # ==========================================
    
    @commands.command()
    async def startrotator(self, ctx, *, args):
        """
        starts a custom status rotator for this session.
        usage: .startrotator status1, status2, status3 | 10m
        example: .startrotator grinding, in the trenches, vibing | 5m
        """
        error_emoji = self.bot.config.get_emoji("error")
        
        # Parse the interval from the end (e.g., 10m, 5s, 2h)
        match = re.search(r'\|\s*(\d+)([smh])$', args)
        if not match:
            return await ctx.send(f"{error_emoji} missing time. usage: `.startrotator status1, status2 | 5m`")

        amount = int(match.group(1))
        unit = match.group(2)
        multiplier = {'s': 1, 'm': 60, 'h': 3600}
        total_seconds = amount * multiplier[unit]

        # Extract statuses
        statuses_str = args[:match.start()].strip()
        statuses = [s.strip() for s in statuses_str.split(",") if s.strip()]

        if not statuses:
            return await ctx.send(f"{error_emoji} no statuses provided.")

        if self.custom_rotator_task and not self.custom_rotator_task.done():
            self.custom_rotator_task.cancel()

        self.bot.locked_presence = True
        self.custom_rotator_task = asyncio.create_task(self._run_custom_rotator(statuses, total_seconds))
        
        success_emoji = self.bot.config.get_emoji("success")
        await ctx.send(f"{success_emoji} custom rotator started with {len(statuses)} statuses every {amount}{unit}.")

    async def _run_custom_rotator(self, statuses, interval):
        try:
            index = 0
            while True:
                current = statuses[index % len(statuses)]
                await self.bot.change_presence(activity=discord.CustomActivity(name=current))
                index += 1
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            pass

    @commands.command()
    async def stoprotator(self, ctx):
        """stops the custom status rotator"""
        if self.custom_rotator_task and not self.custom_rotator_task.done():
            self.custom_rotator_task.cancel()
            self.bot.locked_presence = False
            await self.bot.change_presence(activity=None)
            emoji = self.bot.config.get_emoji("success")
            await ctx.send(f"{emoji} custom rotator stopped.")
        else:
            error = self.bot.config.get_emoji("error")
            await ctx.send(f"{error} no rotator is currently running.")

async def setup(bot):
    await bot.add_cog(Presence(bot))
