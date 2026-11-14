import discord
from discord.ext import commands
from datetime import datetime
import asyncio
import re

class Presence(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.custom_rotator_task = None
        # Store the current RPC state so we can edit icons independently
        self.current_activity_type = None
        self.current_name = None
        self.current_details = None
        self.current_state = None
        self.current_large_img = None
        self.current_small_img = None
        self.current_elapsed = None

    def cog_unload(self):
        if self.custom_rotator_task and not self.custom_rotator_task.done():
            self.custom_rotator_task.cancel()

    async def _update_presence(self):
        """Internal helper to apply the current saved state"""
        if not self.current_activity_type:
            return
            
        types = {
            "playing": discord.ActivityType.playing,
            "watching": discord.ActivityType.watching,
            "listening": discord.ActivityType.listening,
            "competing": discord.ActivityType.competing
        }
        
        assets = {}
        if self.current_large_img:
            assets["large_image"] = self.current_large_img
            if self.current_details:
                assets["large_text"] = self.current_details
        if self.current_small_img:
            assets["small_image"] = self.current_small_img
            if self.current_state:
                assets["small_text"] = self.current_state

        timestamps = {"start": int(datetime.now().timestamp())} if self.current_elapsed else None

        self.bot.locked_presence = True
        await self.bot.change_presence(activity=discord.Activity(
            type=types[self.current_activity_type],
            name=self.current_name,
            details=self.current_details,
            state=self.current_state,
            assets=assets if assets else None,
            timestamps=timestamps
        ))

    @commands.command()
    async def rpc(self, ctx, activity_type: str, *, args):
        """advanced rpc. usage: .rpc playing name | details | state | large_img | small_img | elapsed"""
        self.current_activity_type = activity_type.lower()
        
        if self.current_activity_type not in ["playing", "watching", "listening", "competing", "streaming", "stream"]:
            return await ctx.send(f"{self.bot.config.get_emoji('error')} invalid type.")

        parts = [p.strip() for p in args.split("|")]
        self.current_name = parts[0] if len(parts) > 0 else "chrm"

        self.current_elapsed = False
        if len(parts) > 0 and parts[-1].lower() == "elapsed":
            self.current_elapsed = True
            parts.pop()

        if ctx.message.attachments:
            self.current_large_img = ctx.message.attachments[0].url
        elif len(parts) > 3 and parts[3]:
            self.current_large_img = parts[3]
        else:
            self.current_large_img = None

        self.current_details = parts[1] if len(parts) > 1 and parts[1] else None
        self.current_state = parts[2] if len(parts) > 2 and parts[2] else None
        self.current_small_img = parts[4] if len(parts) > 4 and parts[4] else None

        if self.current_activity_type in ["streaming", "stream"]:
            if len(parts) < 2:
                return await ctx.send(f"{self.bot.config.get_emoji('error')} streaming requires a url.")
            self.bot.locked_presence = True
            await self.bot.change_presence(activity=discord.Streaming(name=self.current_name, url=parts[1]))
            return await ctx.send(f"{self.bot.config.get_emoji('success')} streaming updated.")

        try:
            await self._update_presence()
            await ctx.send(f"{self.bot.config.get_emoji('success')} rpc updated: {self.current_activity_type} **{self.current_name}**")
        except Exception as e:
            await ctx.send(f"{self.bot.config.get_emoji('error')} error: {e}")

    @commands.command()
    async def iconplay(self, ctx, url: str = None):
        """changes ONLY the large icon. usage: .iconplay <url> (or attach an image)"""
        if ctx.message.attachments:
            url = ctx.message.attachments[0].url
        if not url:
            return await ctx.send(f"{self.bot.config.get_emoji('error')} provide a url or attach an image.")
        
        self.current_large_img = url
        await self._update_presence()
        await ctx.send(f"{self.bot.config.get_emoji('success')} large icon updated.")

    @commands.command()
    async def smalliconplay(self, ctx, url: str = None):
        """changes ONLY the small icon. usage: .smalliconplay <url> (or attach an image)"""
        if ctx.message.attachments:
            url = ctx.message.attachments[0].url
        if not url:
            return await ctx.send(f"{self.bot.config.get_emoji('error')} provide a url or attach an image.")
        
        self.current_small_img = url
        await self._update_presence()
        await ctx.send(f"{self.bot.config.get_emoji('success')} small icon updated.")

    @commands.command()
    async def clearstatus(self, ctx):
        """forcefully wipes the active rpc"""
        self.current_activity_type = None
        self.bot.locked_presence = False
        if self.custom_rotator_task and not self.custom_rotator_task.done():
            self.custom_rotator_task.cancel()
        await self.bot.change_presence(activity=None)
        await ctx.send(f"{self.bot.config.get_emoji('success')} presence completely wiped.")

    # --- Rotator Commands ---
    @commands.command()
    async def startrotator(self, ctx, *, args):
        match = re.search(r'\|\s*(\d+)([smh])$', args)
        if not match: return await ctx.send("missing time. usage: `.startrotator status1, status2 | 5m`")
        amount, unit = int(match.group(1)), match.group(2)
        total_seconds = amount * {'s': 1, 'm': 60, 'h': 3600}[unit]
        statuses = [s.strip() for s in args[:match.start()].strip().split(",") if s.strip()]
        if not statuses: return await ctx.send("no statuses provided.")
        if self.custom_rotator_task and not self.custom_rotator_task.done(): self.custom_rotator_task.cancel()
        self.bot.locked_presence = True
        self.custom_rotator_task = asyncio.create_task(self._run_custom_rotator(statuses, total_seconds))
        await ctx.send(f"{self.bot.config.get_emoji('success')} rotator started.")

    async def _run_custom_rotator(self, statuses, interval):
        try:
            index = 0
            while True:
                await self.bot.change_presence(activity=discord.CustomActivity(name=statuses[index % len(statuses)]))
                index += 1
                await asyncio.sleep(interval)
        except asyncio.CancelledError: pass

    @commands.command()
    async def stoprotator(self, ctx):
        if self.custom_rotator_task and not self.custom_rotator_task.done():
            self.custom_rotator_task.cancel()
            self.bot.locked_presence = False
            await self.bot.change_presence(activity=None)
            await ctx.send(f"{self.bot.config.get_emoji('success')} rotator stopped.")

async def setup(bot):
    await bot.add_cog(Presence(bot))
