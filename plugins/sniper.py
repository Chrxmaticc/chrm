import discord
from discord.ext import commands
from collections import deque

class Sniper(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Store last 100 deleted messages per channel
        self.deleted_cache = {}
        # Store last 100 edited messages per channel
        self.edited_cache = {}

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if not message.guild or message.author.bot:
            return
        
        if message.channel.id not in self.deleted_cache:
            self.deleted_cache[message.channel.id] = deque(maxlen=100)
            
        self.deleted_cache[message.channel.id].append(message)

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if not before.guild or before.author.bot or before.content == after.content:
            return

        if before.channel.id not in self.edited_cache:
            self.edited_cache[before.channel.id] = deque(maxlen=100)

        self.edited_cache[before.channel.id].append(before)

    @commands.command()
    async def snipe(self, ctx, index: int = 1):
        """snipes a deleted message. usage: .snipe or .snipe 2"""
        if not self.deleted_cache.get(ctx.channel.id):
            error = self.bot.config.get_emoji("error")
            return await ctx.send(f"{error} nothing to snipe.")

        try:
            # index 1 is the most recent, index 2 is the one before it, etc.
            msg = self.deleted_cache[ctx.channel.id][-index]
        except IndexError:
            error = self.bot.config.get_emoji("error")
            return await ctx.send(f"{error} no message at that index.")

        embed = discord.Embed(description=msg.content if msg.content else "*[no text]*", color=0x2b2d31)
        embed.set_author(name=msg.author.name, icon_url=msg.author.display_avatar.url)
        embed.set_footer(text=f"sniped by chrm • {index}/{len(self.deleted_cache[ctx.channel.id])}")

        # Attach image if the deleted message had one
        if msg.attachments:
            embed.set_image(url=msg.attachments[0].url)

        await ctx.send(embeds=[embed])

    @commands.command()
    async def editsnipe(self, ctx, index: int = 1):
        """snipes an edited message. usage: .editsnipe"""
        if not self.edited_cache.get(ctx.channel.id):
            error = self.bot.config.get_emoji("error")
            return await ctx.send(f"{error} nothing to editsnipe.")

        try:
            msg = self.edited_cache[ctx.channel.id][-index]
        except IndexError:
            error = self.bot.config.get_emoji("error")
            return await ctx.send(f"{error} no message at that index.")

        embed = discord.Embed(title="edited message", description=msg.content, color=0x2b2d31)
        embed.set_author(name=msg.author.name, icon_url=msg.author.display_avatar.url)
        embed.set_footer(text=f"editsniped by chrm")

        await ctx.send(embeds=[embed])

async def setup(bot):
    await bot.add_cog(Sniper(bot))
