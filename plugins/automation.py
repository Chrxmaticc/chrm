import discord
from discord.ext import commands
import os
import aiohttp

class Automation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _save_feature(self, feature_key, data):
        """Updates memory AND saves to the database so the sync loop doesn't wipe it."""
        if "features" not in self.bot.config.data:
            self.bot.config.data["features"] = {}
        
        self.bot.config.data["features"][feature_key] = data

        base_api = os.environ.get("BASE_API_URL", "https://chrm-api.onrender.com")
        try:
            async with aiohttp.ClientSession() as session:
                payload = {"settings": {"features": self.bot.config.data["features"]}}
                await session.patch(f"{base_api}/api/user/{self.bot.user_id}", json=payload)
        except Exception as e:
            print(f"[AUTOMATION] Failed to save to API: {e}")

    @commands.Cog.listener()
    async def on_message(self, message):
        # Ignore our own messages
        if message.author.id == self.bot.user.id or not message.content:
            return

        content_lower = message.content.lower()

        # --- AFK CHECK ---
        afk = self.bot.config.data.get("features", {}).get("afk", {})
        if afk.get("enabled") and self.bot.user.mentioned_in(message):
            await self.bot.human_delay()
            return await message.reply(afk.get("message", "afk"), mention_author=True)

        # --- AUTORESPOND CHECK ---
        autorespond = self.bot.config.data.get("features", {}).get("autorespond", {})
        for trigger, response in autorespond.items():
            # If the trigger word is in the message
            if trigger.lower() in content_lower:
                await self.bot.human_delay()
                await message.channel.send(response)
                break # Stop checking other triggers once one fires

        # --- AUTOREACT CHECK ---
        autoreact = self.bot.config.data.get("features", {}).get("autoreact", {})
        for trigger, emoji in autoreact.items():
            if trigger.lower() in content_lower:
                await self.bot.human_delay()
                try:
                    await message.add_reaction(emoji)
                except Exception as e:
                    print(f"[AUTOMATION] Failed to react: {e}")
                break

    # --- COMMANDS ---

    @commands.command()
    async def addrespond(self, ctx, trigger: str, *, response: str):
        """adds an auto-responder. usage: .addrespond hello hi there"""
        autorespond = self.bot.config.data.get("features", {}).get("autorespond", {})
        autorespond[trigger.lower()] = response
        await self._save_feature("autorespond", autorespond)
        
        emoji = self.bot.config.get_emoji("success")
        await ctx.send(f"{emoji} will now respond to `{trigger.lower()}`")

    @commands.command()
    async def addreact(self, ctx, trigger: str, emoji: str):
        """adds an auto-reactor. usage: .addreact lol 😂"""
        autoreact = self.bot.config.data.get("features", {}).get("autoreact", {})
        autoreact[trigger.lower()] = emoji
        await self._save_feature("autoreact", autoreact)
        
        success = self.bot.config.get_emoji("success")
        await ctx.send(f"{success} will now react to `{trigger.lower()}` with {emoji}")

    @commands.command()
    async def removerespond(self, ctx, trigger: str):
        """removes an auto-responder. usage: .removerespond hello"""
        autorespond = self.bot.config.data.get("features", {}).get("autorespond", {})
        if trigger.lower() in autorespond:
            del autorespond[trigger.lower()]
            await self._save_feature("autorespond", autorespond)
            emoji = self.bot.config.get_emoji("success")
            await ctx.send(f"{emoji} removed auto-responder for `{trigger.lower()}`")
        else:
            error = self.bot.config.get_emoji("error")
            await ctx.send(f"{error} trigger `{trigger.lower()}` not found.")

    @commands.command()
    async def removereact(self, ctx, trigger: str):
        """removes an auto-reactor. usage: .removereact lol"""
        autoreact = self.bot.config.data.get("features", {}).get("autoreact", {})
        if trigger.lower() in autoreact:
            del autoreact[trigger.lower()]
            await self._save_feature("autoreact", autoreact)
            emoji = self.bot.config.get_emoji("success")
            await ctx.send(f"{emoji} removed auto-reactor for `{trigger.lower()}`")
        else:
            error = self.bot.config.get_emoji("error")
            await ctx.send(f"{error} trigger `{trigger.lower()}` not found.")

    @commands.command()
    async def afk(self, ctx, *, msg="afk"):
        """enable afk mode. usage: .afk sleeping"""
        afk_data = {"enabled": True, "message": msg}
        await self._save_feature("afk", afk_data)
        
        emoji = self.bot.config.get_emoji("success")
        await ctx.send(f"{emoji} afk enabled: {msg}")

    @commands.command()
    async def unafk(self, ctx):
        """disable afk mode"""
        afk_data = {"enabled": False, "message": "afk"}
        await self._save_feature("afk", afk_data)
        
        emoji = self.bot.config.get_emoji("success")
        await ctx.send(f"{emoji} welcome back. afk disabled.")

async def setup(bot):
    await bot.add_cog(Automation(bot))
