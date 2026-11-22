import discord
from discord.ext import commands
import os
import psutil

# Your Discord ID
from .helpers import OWNER_ID, is_owner


class OwnerMixin:
    """Commands for this sub-cog; assembled into the package cog."""
    @commands.command()
    @is_owner()
    async def restart(self, ctx):
        """force restarts your selfbot instance."""
        await ctx.send(f"{self.bot.config.get_emoji('success')} restarting engine instance. see you in 30 seconds...")
        # Closing the bot triggers the sync loop to reboot it
        await self.bot.close()

    @commands.command()
    @is_owner()
    async def reload(self, ctx, plugin: str):
        """reloads a plugin package without restarting. usage: .reload fun"""
        try:
            await self.bot.reload_extension(f"plugins.{plugin}")
            await ctx.send(f"{self.bot.config.get_emoji('success')} reloaded `plugins/{plugin}`")
        except Exception as e:
            await ctx.send(f"{self.bot.config.get_emoji('error')} failed to reload: {e}")

    @commands.command()
    @is_owner()
    async def sysinfo(self, ctx):
        """shows engine stats"""
        process = psutil.Process(os.getpid())
        mem = process.memory_info().rss / 1024 / 1024 # MB
        
        text = (
            f"**engine system info**\n"
            f"**ram usage:** {mem:.2f} MB\n"
            f"**cpu usage:** {psutil.cpu_percent()}%\n"
            f"**platform:** {self.bot.ws.platform}\n"
            f"**latency:** {round(self.bot.latency * 1000)}ms"
        )
        await ctx.send(text)
