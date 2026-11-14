import discord
from discord.ext import commands
import asyncio

class Utility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user) # 1 use per 5 seconds
    async def purge(self, ctx, amount: int = 50):
        """purges your own messages. usage: .purge 50"""
        error = self.bot.config.get_emoji("error")
        success = self.bot.config.get_emoji("success")

        if amount > 100:
            return await ctx.send(f"{error} max purge limit is 100 to prevent rate limits.")
        
        # Delete the command message first
        try:
            await ctx.message.delete()
        except:
            pass

        # Check to make sure it's only your messages
        def is_me(m):
            return m.author.id == self.bot.user.id

        try:
            # channel.purge handles the rate limits safely in the background
            deleted = await ctx.channel.purge(limit=amount, check=is_me)
            
            # Send confirmation and auto-delete it after 3 seconds
            msg = await ctx.send(f"{success} purged {len(deleted)} of your messages.")
            await asyncio.sleep(3)
            await msg.delete()
            
        except discord.Forbidden:
            await ctx.send(f"{error} i don't have permission to delete messages in this channel.")
        except Exception as e:
            await ctx.send(f"{error} failed to purge: {e}")

    @commands.command()
    async def blacktea(self, ctx):
        emoji = self.bot.config.get_emoji("tea")
        await ctx.send(f"{emoji} brewing the finest black tea... absolutely bussin.")

async def setup(bot):
    await bot.add_cog(Utility(bot))
