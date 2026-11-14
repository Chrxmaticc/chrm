import discord
from discord.ext import commands, tasks
import itertools

class Presence(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
        # Ensure the feature exists in config safely
        if "features" not in self.bot.config.data:
            self.bot.config.data["features"] = {}
        if "status_rotator" not in self.bot.config.data["features"]:
            self.bot.config.data["features"]["status_rotator"] = {
                "enabled": True,
                "statuses": ["chrm on top", "vibing", "afk", "learning python"]
            }

        self.statuses = itertools.cycle(self.bot.config.data["features"]["status_rotator"]["statuses"])
        self.rotate_status.start()

    def cog_unload(self):
        self.rotate_status.cancel()

    @tasks.loop(seconds=60)
    async def rotate_status(self):
        # Check if the user disabled the rotator OR if they have a locked presence
        if not self.bot.config.data["features"]["status_rotator"].get("enabled", True):
            return
            
        if self.bot.is_ready() and not getattr(self.bot, 'locked_presence', False):
            current = next(self.statuses)
            await self.bot.change_presence(activity=discord.CustomActivity(name=current))

    @rotate_status.before_loop
    async def before_rotate(self):
        await self.bot.wait_until_ready()

    @commands.command()
    async def togglerotator(self, ctx):
        """turns the automatic status rotator on or off"""
        current = self.bot.config.data["features"]["status_rotator"].get("enabled", True)
        self.bot.config.data["features"]["status_rotator"]["enabled"] = not current
        
        emoji = self.bot.config.get_emoji("success")
        state = "ON" if not current else "OFF"
        
        if not current:
            self.statuses = itertools.cycle(self.bot.config.data["features"]["status_rotator"]["statuses"])
            
        await ctx.send(f"{emoji} status rotator is now **{state}**.")

    @commands.command()
    async def addstatus(self, ctx, *, status: str):
        """adds a custom status to the rotator. usage: .addstatus sipping tea"""
        self.bot.config.data["features"]["status_rotator"]["statuses"].append(status)
        self.statuses = itertools.cycle(self.bot.config.data["features"]["status_rotator"]["statuses"])
        
        emoji = self.bot.config.get_emoji("success")
        await ctx.send(f"{emoji} added `{status}` to the status rotator.")

    @commands.command()
    async def clearstatuses(self, ctx):
        """clears all custom statuses and resets to default"""
        self.bot.config.data["features"]["status_rotator"]["statuses"] = ["chrm on top", "vibing"]
        self.statuses = itertools.cycle(self.bot.config.data["features"]["status_rotator"]["statuses"])
        
        emoji = self.bot.config.get_emoji("success")
        await ctx.send(f"{emoji} status rotator list reset.")

    @commands.command()
    async def rpc(self, ctx, activity_type: str, *, args):
        """
        advanced rpc. 
        usage: .rpc playing name | details | state | image_url
        usage for streaming: .rpc streaming title | url
        """
        activity_type = activity_type.lower()
        
        # Parse the arguments
        parts = [p.strip() for p in args.split("|")]
        name = parts[0] if len(parts) > 0 else "chrm"

        # Special handler for Streaming (requires a URL)
        if activity_type in ["streaming", "stream"]:
            if len(parts) < 2:
                error = self.bot.config.get_emoji("error")
                return await ctx.send(f"{error} streaming requires a url. usage: `.rpc streaming title | url`")
            
            url = parts[1]
            if not url.startswith("http"):
                error = self.bot.config.get_emoji("error")
                return await ctx.send(f"{error} url must start with http or https.")

            try:
                self.bot.locked_presence = True
                await self.bot.change_presence(activity=discord.Streaming(name=name, url=url))
                emoji = self.bot.config.get_emoji("success")
                await ctx.send(f"{emoji} now streaming: **{name}** at {url}")
            except Exception as e:
                await ctx.send(f"error: {e}")
            return

        # Standard RPC handler
        types = {
            "playing": discord.ActivityType.playing,
            "watching": discord.ActivityType.watching,
            "listening": discord.ActivityType.listening,
            "competing": discord.ActivityType.competing
        }
        
        if activity_type not in types:
            error = self.bot.config.get_emoji("error")
            return await ctx.send(f"{error} invalid type. use playing, watching, listening, competing, or streaming.")

        details = parts[1] if len(parts) > 1 else None
        state = parts[2] if len(parts) > 2 else None
        image_url = parts[3] if len(parts) > 3 else None

        assets = {}
        if image_url:
            assets["large_image"] = image_url
            if details:
                assets["large_text"] = details

        try:
            self.bot.locked_presence = True
            await self.bot.change_presence(activity=discord.Activity(
                type=types[activity_type],
                name=name,
                details=details,
                state=state,
                assets=assets if assets else None
            ))
            emoji = self.bot.config.get_emoji("success")
            await ctx.send(f"{emoji} rpc updated: {activity_type} **{name}**")
        except Exception as e:
            await ctx.send(f"error: {e}")

    @commands.command()
    async def customstatus(self, ctx, *, text):
        self.bot.locked_presence = True
        await self.bot.change_presence(activity=discord.CustomActivity(name=text))
        emoji = self.bot.config.get_emoji("success")
        await ctx.send(f"{emoji} custom status set: {text}")

    @commands.command()
    async def clearstatus(self, ctx):
        self.bot.locked_presence = False
        emoji = self.bot.config.get_emoji("success")
        await ctx.send(f"{emoji} presence cleared. rotator will take over.")

async def setup(bot):
    await bot.add_cog(Presence(bot))
