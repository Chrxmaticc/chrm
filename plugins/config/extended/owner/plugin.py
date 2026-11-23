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
        """reloads (or first-loads) a plugin package. usage: .reload fun"""
        name = f"plugins.{plugin}"
        success = self.bot.config.get_emoji("success")
        error = self.bot.config.get_emoji("error")
        # A package whose import failed at startup is not "loaded", and
        # reload_extension would only say so. Load it instead, so the real error
        # (usually a missing module) is what gets reported.
        action = "reload" if name in self.bot.extensions else "load"
        try:
            if action == "reload":
                await self.bot.reload_extension(name)
            else:
                await self.bot.load_extension(name)
        except Exception as e:
            getattr(self.bot, "load_errors", {}).pop(name, None)
            return await ctx.send(f"{error} failed to {action}: {type(e).__name__}: {e}")

        getattr(self.bot, "load_errors", {}).pop(name, None)
        await ctx.send(f"{success} {action}ed `plugins/{plugin}`")

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

        # A plugin that failed to import has no commands, so the only symptom is
        # silence. Surface the reason here instead of only in the host logs.
        failures = getattr(self.bot, "load_errors", None)
        if failures:
            lines = [f"`{name}` -- {reason[:200]}" for name, reason in failures.items()]
            text += "\n**failed plugins:**\n" + "\n".join(lines)

        await ctx.send(text)
