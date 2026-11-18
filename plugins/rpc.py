import discord
from discord.ext import commands
import asyncio
import re
from datetime import datetime
import hashlib

def format_image_url(url):
    if not url:
        return None
    if url.startswith("mp:") or url.startswith("spotify:"):
        return url
    if "cdn.discordapp.com" in url or "media.discordapp.net" in url:
        return url.split("?")[0]
    if url.startswith("http"):
        url_hash = hashlib.md5(url.encode()).hexdigest()
        clean_url = url.replace("https://", "").replace("http://", "")
        return f"mp:external/{url_hash}/https/{clean_url}"
    return url

# ==========================================
# 1. MODALS
# ==========================================
class RPMModal(discord.ui.Modal, title="Set Rich Presence"):
    def __init__(self, cog, act_type):
        super().__init__()
        self.cog = cog
        self.act_type = act_type
        
        self.name = discord.ui.TextInput(label="App/Game Name", placeholder="e.g. Minecraft", required=True)
        self.details = discord.ui.TextInput(label="Details (Line 1)", required=False)
        self.state = discord.ui.TextInput(label="State (Line 2)", required=False)
        self.image = discord.ui.TextInput(label="Discord CDN Image URL", placeholder="https://cdn.discordapp.com/...", required=False)
        
        self.add_item(self.name)
        self.add_item(self.details)
        self.add_item(self.state)
        self.add_item(self.image)

    async def on_submit(self, interaction: discord.Interaction):
        types = {
            "playing": discord.ActivityType.playing,
            "listening": discord.ActivityType.listening,
            "watching": discord.ActivityType.watching
        }
        
        assets = {}
        if self.image.value:
            assets["large_image"] = format_image_url(self.image.value)
            if self.details.value:
                assets["large_text"] = self.details.value

        try:
            self.cog.bot.locked_presence = True
            await self.cog.bot.change_presence(activity=discord.Activity(
                type=types[self.act_type],
                name=self.name.value,
                details=self.details.value,
                state=self.state.value,
                assets=assets if assets else None
            ))
            await interaction.response.send_message(f"✅ RPC updated to **{self.act_type.title()} {self.name.value}**.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to set RPC: {e}", ephemeral=True)

# ==========================================
# 2. BUTTON VIEW (V1)
# ==========================================
class RPCView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None) # No timeout so buttons stay active
        self.cog = cog

    @discord.ui.button(label="Playing", style=discord.ButtonStyle.primary, emoji="🎮")
    async def btn_playing(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RPMModal(self.cog, "playing"))

    @discord.ui.button(label="Listening", style=discord.ButtonStyle.primary, emoji="🎧")
    async def btn_listening(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RPMModal(self.cog, "listening"))

    @discord.ui.button(label="Watching", style=discord.ButtonStyle.primary, emoji="📺")
    async def btn_watching(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RPMModal(self.cog, "watching"))

    @discord.ui.button(label="Clear Status", style=discord.ButtonStyle.danger, emoji="🛑")
    async def btn_clear(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.cog.bot.locked_presence = False
        await self.cog.bot.change_presence(activity=None)
        await interaction.response.send_message("🛑 RPC forcefully cleared.", ephemeral=True)


class RPC(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.custom_rotator_task = None

    def cog_unload(self):
        if self.custom_rotator_task and not self.custom_rotator_task.done():
            self.custom_rotator_task.cancel()

    # ==========================================
    # 3. THE MENU COMMAND
    # ==========================================
    @commands.command()
    async def rpcmenu(self, ctx):
        """opens the interactive rpc manager"""
        embed = discord.Embed(
            title="RPC Manager",
            description="Manage your Rich Presence directly from this menu. Select an activity type below.",
            color=0x2b2d31
        )
        await ctx.send(embed=embed, view=RPCView(self))

    # ==========================================
    # 4. TEXT COMMANDS
    # ==========================================
    @commands.command()
    async def rpc(self, ctx, activity_type: str, *, args):
        """advanced rpc. usage: .rpc playing name | details | state | image | elapsed"""
        activity_type = activity_type.lower()
        parts = [p.strip() for p in args.split("|")]
        name = parts[0] if len(parts) > 0 else "chrm"

        timestamps = None
        if "elapsed" in [p.lower() for p in parts]:
            timestamps = {"start": int(datetime.now().timestamp())}
            parts.pop()

        large_img = parts[3] if len(parts) > 3 and parts[3] else None
        details = parts[1] if len(parts) > 1 and parts[1] else None
        state = parts[2] if len(parts) > 2 and parts[2] else None

        types = {"playing": discord.ActivityType.playing, "watching": discord.ActivityType.watching, "listening": discord.ActivityType.listening, "competing": discord.ActivityType.competing}
        if activity_type not in types:
            return await ctx.send(f"{self.bot.config.get_emoji('error')} invalid type.")

        assets = {}
        if large_img:
            assets["large_image"] = format_image_url(large_img)
            if details: assets["large_text"] = details

        try:
            self.bot.locked_presence = True
            await self.bot.change_presence(activity=discord.Activity(
                type=types[activity_type], name=name, details=details, state=state,
                assets=assets if assets else None, timestamps=timestamps
            ))
            await ctx.send(f"{self.bot.config.get_emoji('success')} rpc updated: {activity_type} **{name}**")
        except Exception as e:
            await ctx.send(f"{self.bot.config.get_emoji('error')} error: {e}")

    @commands.command()
    async def stream(self, ctx, url: str, *, title):
        if not url.startswith("http"):
            return await ctx.send(f"{self.bot.config.get_emoji('error')} invalid url.")
        self.bot.locked_presence = True
        await self.bot.change_presence(activity=discord.Streaming(name=title, url=url))
        await ctx.send(f"{self.bot.config.get_emoji('success')} now streaming: **{title}**")

    @commands.command()
    async def customstatus(self, ctx, *, text):
        self.bot.locked_presence = True
        await self.bot.change_presence(activity=discord.CustomActivity(name=text))
        await ctx.send(f"{self.bot.config.get_emoji('success')} custom status set to: {text}")

    @commands.command()
    async def clearstatus(self, ctx):
        self.bot.locked_presence = False
        await self.bot.change_presence(activity=None)
        await ctx.send(f"{self.bot.config.get_emoji('success')} presence completely wiped.")

    # ==========================================
    # 5. STATUS ROTATOR
    # ==========================================
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
    await bot.add_cog(RPC(bot))
