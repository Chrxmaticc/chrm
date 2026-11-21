import discord
from discord.ext import commands
from discord import app_commands
import os
import aiohttp
import time

from api_base import BASE_API

class HelperBot(commands.Bot):
    def __init__(self):
        # We use a dummy prefix because it uses slash commands
        super().__init__(command_prefix="!", intents=discord.Intents.default())
        self.api_url = BASE_API

    async def setup_hook(self):
        await self.tree.sync()
        print("🤖 [HELPER] Synced slash commands.")

    async def on_ready(self):
        print(f"🤖 [HELPER] Logged in as {self.user.name}")

# ==========================================
# UI: MODALS & VIEWS
# ==========================================
class SpotifyModal(discord.ui.Modal, title="Spotify Spoofer"):
    song = discord.ui.TextInput(label="Song Name", placeholder="Blinding Lights", required=True)
    artist = discord.ui.TextInput(label="Artist", placeholder="The Weeknd", required=True)
    duration = discord.ui.TextInput(label="Duration (Seconds)", placeholder="200", default="200", required=True)

    def __init__(self, bot, user_id):
        super().__init__()
        self.bot = bot
        self.user_id = user_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        # We tell the API to set the RPC with a start and end time for the progress bar
        current_time = int(time.time())
        end_time = current_time + int(self.duration.value)
        
        rpc_data = {
            "type": "listening",
            "name": "Spotify",
            "details": self.song.value,
            "state": self.artist.value,
            "start_time": current_time,
            "end_time": end_time
        }

        async with aiohttp.ClientSession() as session:
            # Send to your API (You need to create this endpoint)
            await session.patch(f"{self.bot.api_url}/api/user/{self.user_id}", json={"settings": {"rpc": rpc_data}})
            
        await interaction.followup.send("✅ Spotify spoof sent to engine!", ephemeral=True)

class RPCModal(discord.ui.Modal, title="Custom RPC"):
    app_name = discord.ui.TextInput(label="App Name", placeholder="Minecraft", required=True)
    details = discord.ui.TextInput(label="Details", placeholder="Survival Mode", required=False)
    state = discord.ui.TextInput(label="State", placeholder="Grinding", required=False)
    image = discord.ui.TextInput(label="Image URL", placeholder="https://cdn.discordapp.com/...", required=False)

    def __init__(self, bot, user_id, act_type):
        super().__init__()
        self.bot = bot
        self.user_id = user_id
        self.act_type = act_type

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        rpc_data = {
            "type": self.act_type,
            "name": self.app_name.value,
            "details": self.details.value,
            "state": self.state.value,
            "image_url": self.image.value
        }
        async with aiohttp.ClientSession() as session:
            await session.patch(f"{self.bot.api_url}/api/user/{self.user_id}", json={"settings": {"rpc": rpc_data}})
        await interaction.followup.send("✅ RPC sent to engine!", ephemeral=True)

class DashboardView(discord.ui.View):
    def __init__(self, bot, user_id):
        super().__init__(timeout=None)
        self.bot = bot
        self.user_id = user_id

    @discord.ui.button(label="Spotify Spoof", style=discord.ButtonStyle.success, emoji="🎵")
    async def spotify_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SpotifyModal(self.bot, self.user_id))

    @discord.ui.button(label="Playing", style=discord.ButtonStyle.primary, emoji="🎮")
    async def playing_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RPCModal(self.bot, self.user_id, "playing"))

    @discord.ui.button(label="Clear RPC", style=discord.ButtonStyle.danger, emoji="🛑")
    async def clear_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        async with aiohttp.ClientSession() as session:
            await session.patch(f"{self.bot.api_url}/api/user/{self.user_id}", json={"settings": {"rpc": {}}})
        await interaction.followup.send("🛑 RPC cleared.", ephemeral=True)

# ==========================================
# COG
# ==========================================
class Helper(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.helper = HelperBot()
        
        # Register commands to the helper bot
        @self.helper.tree.command(name="menu", description="Open the chrm control panel")
        async def menu(interaction: discord.Interaction):
            embed = discord.Embed(
                title="chrm control panel",
                description="Manage your engine directly from Discord.",
                color=0x2b2d31
            )
            await interaction.response.send_message(embed=embed, view=DashboardView(self.helper, interaction.user.id), ephemeral=True)

        @self.helper.tree.command(name="host", description="Check engine status and RAM usage")
        async def host(interaction: discord.Interaction):
            import psutil
            process = psutil.Process(os.getpid())
            ram = process.memory_info().rss / 1024 / 1024
            embed = discord.Embed(title="Engine Host", color=0x00ff00)
            embed.add_field(name="Status", value="🟢 Online")
            embed.add_field(name="RAM Usage", value=f"{ram:.1f} MB / 512 MB")
            embed.add_field(name="Uptime", value="Active")
            await interaction.response.send_message(embed=embed, ephemeral=True)

    async def cog_load(self):
        token = os.environ.get("BOT_TOKEN")
        if token:
            print("🤖 [HELPER] Starting helper bot...")
            asyncio.create_task(self.helper.start(token))
        else:
            print("⚠️ [HELPER] No BOT_TOKEN found. Helper bot disabled.")

async def setup(bot):
    await bot.add_cog(Helper(bot))
