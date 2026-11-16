import discord
from discord.ext import commands
import os
import psutil

# Your Discord ID
OWNER_ID = 1527403360880431275

def is_owner():
    async def predicate(ctx):
        # Only allows the command if the invoker's ID matches yours
        return ctx.author.id == OWNER_ID
    return commands.check(predicate)

class Owner(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

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
        """reloads a specific plugin without restarting. usage: .reload presence"""
        try:
            await self.bot.reload_extension(f"plugins.{plugin}")
            await ctx.send(f"{self.bot.config.get_emoji('success')} reloaded `{plugin}.py`")
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

async def setup(bot):
    await bot.add_cog(Owner(bot))
