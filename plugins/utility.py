import discord
from discord.ext import commands
import asyncio

class Utility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def purge(self, ctx, amount: int = 50):
        """purges your own messages. usage: .purge 50"""
        error = self.bot.config.get_emoji("error")
        success = self.bot.config.get_emoji("success")

        if amount > 100:
            return await ctx.send(f"{error} max purge limit is 100 to prevent rate limits.")
        
        try:
            await ctx.message.delete()
        except:
            pass

        def is_me(m):
            return m.author.id == self.bot.user.id

        try:
            # Check if we are in a DM
            if isinstance(ctx.channel, discord.DMChannel):
                deleted_count = 0
                # Fetch history and delete one by one
                async for message in ctx.channel.history(limit=amount):
                    if message.author.id == self.bot.user.id:
                        try:
                            await message.delete()
                            deleted_count += 1
                            await asyncio.sleep(0.5) # Small delay to prevent rate limits in DMs
                        except:
                            pass
                
                msg = await ctx.send(f"{success} purged {deleted_count} of your messages (dm mode).")
                await asyncio.sleep(3)
                await msg.delete()

            else:
                # We are in a server, use the fast bulk delete
                deleted = await ctx.channel.purge(limit=amount, check=is_me)
                msg = await ctx.send(f"{success} purged {len(deleted)} of your messages.")
                await asyncio.sleep(3)
                await msg.delete()
            
        except discord.Forbidden:
            await ctx.send(f"{error} i don't have permission to delete messages here.")
        except Exception as e:
            await ctx.send(f"{error} failed to purge: {e}")

    @commands.command()
    async def blacktea(self, ctx):
        emoji = self.bot.config.get_emoji("tea")
        await ctx.send(f"{emoji} brewing the finest black tea... absolutely bussin.")

async def setup(bot):
    await bot.add_cog(Utility(bot))
