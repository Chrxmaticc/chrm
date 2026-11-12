import discord
from discord.ext import commands

class Utility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def purge(self, ctx, amount: int):
        await ctx.message.delete()
        def is_me(m):
            return m.author == self.bot.user
        
        deleted = await ctx.channel.purge(limit=amount, check=is_me)
        emoji = self.bot.config.get_emoji("success")
        msg = await ctx.send(f"{emoji} purged {len(deleted)} messages.")
        await msg.delete(delay=3)

    @commands.command()
    async def blacktea(self, ctx):
        emoji = self.bot.config.get_emoji("tea")
        await ctx.send(f"{emoji} brewing the finest black tea... absolutely bussin.")

async def setup(bot):
    await bot.add_cog(Utility(bot))
