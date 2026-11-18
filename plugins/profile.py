import discord
from discord.ext import commands, tasks
import os
import aiohttp
import asyncio
import random
import base64

from api_base import BASE_API

class Profile(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.rotate_profile.start()

    def cog_unload(self):
        self.rotate_profile.cancel()

    async def _save_feature(self, feature_key, data):
        if "features" not in self.bot.config.data:
            self.bot.config.data["features"] = {}
        
        self.bot.config.data["features"][feature_key] = data
        base_api = BASE_API
        try:
            async with aiohttp.ClientSession() as session:
                payload = {"settings": {"features": self.bot.config.data["features"]}}
                await session.patch(f"{base_api}/api/user/{self.bot.user_id}", json=payload)
        except Exception as e:
            print(f"[PROFILE] Failed to save to API: {e}")

    async def _get_image_bytes(self, ctx, url=None):
        if ctx.message.attachments:
            return await ctx.message.attachments[0].read()
        elif url and url.startswith("http"):
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        return await resp.read()
        return None

    # --- MANUAL COMMANDS ---

    @commands.command()
    async def setavatar(self, ctx, url: str = None):
        """changes your avatar. usage: .setavatar (attach image) OR .setavatar <url>"""
        img_bytes = await self._get_image_bytes(ctx, url)
        if not img_bytes:
            return await ctx.send(f"{self.bot.config.get_emoji('error')} attach an image or provide a url.")
        
        try:
            await self.bot.user.edit(avatar=img_bytes)
            await ctx.send(f"{self.bot.config.get_emoji('success')} avatar updated.")
        except Exception as e:
            await ctx.send(f"{self.bot.config.get_emoji('error')} failed: {e}")

    @commands.command()
    async def setbanner(self, ctx, url: str = None):
        """changes your banner. usage: .setbanner (attach image) OR .setbanner <url>"""
        img_bytes = await self._get_image_bytes(ctx, url)
        if not img_bytes:
            return await ctx.send(f"{self.bot.config.get_emoji('error')} attach an image or provide a url.")
        
        try:
            # discord.py-self supports banner in edit() via API v9
            await self.bot.user.edit(banner=img_bytes)
            await ctx.send(f"{self.bot.config.get_emoji('success')} banner updated.")
        except Exception as e:
            await ctx.send(f"{self.bot.config.get_emoji('error')} failed: {e}")

    @commands.command()
    async def setname(self, ctx, *, name: str):
        """changes your display name. usage: .setname chrxm"""
        try:
            await self.bot.user.edit(global_name=name)
            await ctx.send(f"{self.bot.config.get_emoji('success')} display name updated to **{name}**.")
        except Exception as e:
            await ctx.send(f"{self.bot.config.get_emoji('error')} failed: {e}")

    # --- ROTATION SETUP ---
    
    @commands.command()
    async def addrotation(self, ctx, rotation_type: str, url: str = None):
        """adds a profile pic/banner to the rotation list. usage: .addrotation avatar (attach image)"""
        rotation_type = rotation_type.lower()
        if rotation_type not in ["avatar", "banner"]:
            return await ctx.send(f"{self.bot.config.get_emoji('error')} type must be 'avatar' or 'banner'.")

        img_bytes = await self._get_image_bytes(ctx, url)
        if not img_bytes:
            return await ctx.send(f"{self.bot.config.get_emoji('error')} attach an image or provide a url.")

        # We have to upload the image to Discord's CDN so we can rotate it later.
        # We do this by sending it to a hidden channel or using the API webhook.
        # For simplicity, we'll just save the URL if provided, or base64 string if uploaded.
        # NOTE: Storing Base64 in Neon uses a lot of space. URL is better.
        img_b64 = base64.b64encode(img_bytes).decode('utf-8')
        
        rotations = self.bot.config.data.get("features", {}).get("rotations", {"avatars": [], "banners": []})
        rotations[rotation_type + "s"].append(img_b64)
        
        await self._save_feature("rotations", rotations)
        emoji = self.bot.config.get_emoji("success")
        await ctx.send(f"{emoji} added to {rotation_type} rotation. total: {len(rotations[rotation_type + 's'])}")

    @commands.command()
    async def startrotation(self, ctx, hours: int = 6):
        """starts profile rotation every X hours. usage: .startrotation 6"""
        rotations = self.bot.config.data.get("features", {}).get("rotations", {"avatars": [], "banners": []})
        
        if not rotations.get("avatars") and not rotations.get("banners"):
            return await ctx.send(f"{self.bot.config.get_emoji('error')} no avatars or banners added yet.")

        # Save interval and enable
        rotation_config = {"enabled": True, "interval_hours": hours}
        await self._save_feature("rotation_config", rotation_config)
        
        self.rotate_profile.change_interval(hours=hours)
        if not self.rotate_profile.is_running():
            self.rotate_profile.start()
            
        emoji = self.bot.config.get_emoji("success")
        await ctx.send(f"{emoji} profile rotation enabled every {hours} hours.")

    @commands.command()
    async def stoprotation(self, ctx):
        """stops profile rotation"""
        rotation_config = {"enabled": False, "interval_hours": 6}
        await self._save_feature("rotation_config", rotation_config)
        self.rotate_profile.cancel()
        await ctx.send(f"{self.bot.config.get_emoji('success')} profile rotation stopped.")

    @tasks.loop(hours=6)
    async def rotate_profile(self):
        """The background loop that swaps the images."""
        if not self.bot.is_ready():
            return

        config = self.bot.config.data.get("features", {}).get("rotation_config", {})
        if not config.get("enabled"):
            return

        rotations = self.bot.config.data.get("features", {}).get("rotations", {"avatars": [], "banners": []})
        
        try:
            if rotations.get("avatars"):
                chosen_avatar = random.choice(rotations["avatars"])
                await self.bot.user.edit(avatar=base64.b64decode(chosen_avatar))
                print("[PROFILE] rotated avatar")
                await asyncio.sleep(5) # Cooldown between edits

            if rotations.get("banners"):
                chosen_banner = random.choice(rotations["banners"])
                await self.bot.user.edit(banner=base64.b64decode(chosen_banner))
                print("[PROFILE] rotated banner")
                
        except Exception as e:
            print(f"[PROFILE] rotation failed: {e}")

    @rotate_profile.before_loop
    async def before_rotate(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(Profile(bot))
