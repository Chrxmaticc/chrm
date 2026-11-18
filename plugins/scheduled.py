import discord
from discord.ext import commands, tasks
import os
import aiohttp
import time
import re
import uuid

from api_base import BASE_API

class Scheduled(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_schedules.start()

    def cog_unload(self):
        self.check_schedules.cancel()

    async def _save_feature(self, feature_key, data):
        """Saves schedules to the DB so they survive restarts."""
        if "features" not in self.bot.config.data:
            self.bot.config.data["features"] = {}
        
        self.bot.config.data["features"][feature_key] = data
        base_api = BASE_API
        try:
            async with aiohttp.ClientSession() as session:
                payload = {"settings": {"features": self.bot.config.data["features"]}}
                await session.patch(f"{base_api}/api/user/{self.bot.user_id}", json=payload)
        except Exception as e:
            print(f"[SCHEDULE] Failed to save to API: {e}")

    def parse_time(self, time_str):
        """Parses '30m', '2h', '1d' into seconds."""
        match = re.match(r"^(\d+)([smhd])$", time_str.lower())
        if not match:
            return None
        amount = int(match.group(1))
        unit = match.group(2)
        multipliers = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}
        return amount * multipliers[unit]

    @commands.command()
    async def schedule(self, ctx, time_str: str, channel: discord.TextChannel, *, message: str):
        """schedules a message. usage: .schedule 30m #general hello world"""
        seconds = self.parse_time(time_str)
        if not seconds:
            return await ctx.send(f"{self.bot.config.get_emoji('error')} invalid time format. use 30s, 5m, 2h, 1d.")

        execute_at = time.time() + seconds
        
        schedules = self.bot.config.data.get("features", {}).get("scheduled_messages", [])
        new_schedule = {
            "id": str(uuid.uuid4()),
            "channel_id": channel.id,
            "message": message,
            "execute_at": execute_at
        }
        schedules.append(new_schedule)
        
        await self._save_feature("scheduled_messages", schedules)
        
        emoji = self.bot.config.get_emoji("success")
        await ctx.send(f"{emoji} scheduled for <t:{int(execute_at)}:R> in {channel.mention}.")

    @commands.command()
    async def alibi(self, ctx, time_str: str, channel: discord.TextChannel, *, message: str):
        """makes you look active by sending a scheduled msg. usage: .alibi 2h #general at work rn"""
        # Alibi is exactly the same as schedule, just a cooler name for it.
        await self.schedule(ctx, time_str, channel, message=message)

    @commands.command()
    async def listschedules(self, ctx):
        """lists your scheduled messages"""
        schedules = self.bot.config.data.get("features", {}).get("scheduled_messages", [])
        if not schedules:
            return await ctx.send("no scheduled messages.")

        text = "**scheduled messages:**\n"
        for s in schedules:
            channel = self.bot.get_channel(s["channel_id"])
            c_name = channel.mention if channel else "unknown-channel"
            text += f"`{s['id'][:6]}` · <t:{int(s['execute_at'])}:R> · {c_name} · {s['message'][:20]}...\n"
        
        await ctx.send(text)

    @commands.command()
    async def clearschedules(self, ctx):
        """clears all schedules"""
        await self._save_feature("scheduled_messages", [])
        await ctx.send(f"{self.bot.config.get_emoji('success')} cleared all schedules.")

    @tasks.loop(seconds=15)
    async def check_schedules(self):
        """Checks every 15 seconds to see if a message needs to be sent."""
        if not self.bot.is_ready():
            return

        schedules = self.bot.config.data.get("features", {}).get("scheduled_messages", [])
        if not schedules:
            return

        now = time.time()
        updated_schedules = []
        needs_update = False

        for s in schedules:
            if now >= s["execute_at"]:
                channel = self.bot.get_channel(s["channel_id"])
                if channel:
                    try:
                        # Add human delay before sending
                        await self.bot.human_delay()
                        await channel.send(s["message"])
                    except Exception as e:
                        print(f"[SCHEDULE] Failed to send: {e}")
                needs_update = True # Don't keep it in the list
            else:
                updated_schedules.append(s)

        if needs_update:
            await self._save_feature("scheduled_messages", updated_schedules)

    @check_schedules.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(Scheduled(bot))
