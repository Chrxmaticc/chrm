import discord
from discord.ext import commands, tasks
import itertools
from datetime import datetime

class Presence(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
        # Ensure features exist in config
        if "features" not in self.bot.config.data:
            self.bot.config.data["features"] = {}
        if "status_rotator" not in self.bot.config.data["features"]:
            self.bot.config.data["features"]["status_rotator"] = {
                "enabled": False, # PERMANENTLY OFF BY DEFAULT
                "statuses": ["chrm on top", "vibing", "afk", "learning python"]
            }

        self.statuses = itertools.cycle(self.bot.config.data["features"]["status_rotator"]["statuses"])
        self.rotate_task = None
        
        # Only start the loop if explicitly enabled
        if self.bot.config.data["features"]["status_rotator"].get("enabled", False):
            self.rotate_task = self.rotate_status.start()

    def cog_unload(self):
        if self.rotate_task:
            self.rotate_task.cancel()

    @tasks.loop(seconds=60)
    async def rotate_status(self):
        if self.bot.is_ready() and not getattr(self.bot, 'locked_presence', False):
            current = next(self.statuses)
            await self.bot.change_presence(activity=discord.CustomActivity(name=current))

    @commands.command()
    async def togglerotator(self, ctx):
        """turns the rotator on or off"""
        current = self.bot.config.data["features"]["status_rotator"].get("enabled", False)
        new_state = not current
        self.bot.config.data["features"]["status_rotator"]["enabled"] = new_state
        
        emoji = self.bot.config.get_emoji("success")
        
        if new_state:
            if not self.rotate_status.is_running():
                self.rotate_status.start()
            await ctx.send(f"{emoji} status rotator is now **ON**.")
        else:
            if self.rotate_status.is_running():
                self.rotate_status.cancel()
            await ctx.send(f"{emoji} status rotator is now **OFF**.")

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

        # Handle Elapsed Timer by removing it from the parts list
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
    async def clearstatus(self, ctx):
        """forcefully wipes the active rpc"""
        self.bot.locked_presence = False
        await self.bot.change_presence(activity=None)
        emoji = self.bot.config.get_emoji("success")
        await ctx.send(f"{emoji} rpc forcefully cleared.")

async def setup(bot):
    await bot.add_cog(Presence(bot))
