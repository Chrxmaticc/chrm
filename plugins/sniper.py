import discord
from discord.ext import commands
from collections import deque

class Sniper(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Store last 50 of each type per channel
        self.deleted_cache = {}
        self.edited_cache = {}
        self.reaction_cache = {}

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if message.author.bot: return
        if message.channel.id not in self.deleted_cache:
            self.deleted_cache[message.channel.id] = deque(maxlen=50)
        self.deleted_cache[message.channel.id].append(message)

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if before.author.bot or before.content == after.content: return
        if before.channel.id not in self.edited_cache:
            self.edited_cache[before.channel.id] = deque(maxlen=50)
        self.edited_cache[before.channel.id].append(before)

    @commands.Cog.listener()
    async def on_reaction_clear(self, message, reactions):
        if message.author.bot: return
        if message.channel.id not in self.reaction_cache:
            self.reaction_cache[message.channel.id] = deque(maxlen=50)
        self.reaction_cache[message.channel.id].append(message)

    @commands.Cog.listener()
    async def on_reaction_remove(self, reaction, user):
        # Sometimes people remove their own reactions
        if user.bot: return
        message = reaction.message
        if message.channel.id not in self.reaction_cache:
            self.reaction_cache[message.channel.id] = deque(maxlen=50)
        
        # Create a fake message object to store the removed reaction info
        fake_msg = type('FakeMsg', (object,), {
            'author': user,
            'content': f"removed reaction {reaction.emoji} from a message",
            'attachments': []
        })()
        self.reaction_cache[message.channel.id].append(fake_msg)

    def _format_attachments(self, msg):
        if not msg.attachments: return ""
        links = "\n".join([f"🔗 {a.url}" for a in msg.attachments])
        return f"\n{links}"

    @commands.command()
    async def snipe(self, ctx, index: int = 1):
        """snipes a deleted message. usage: .snipe or .snipe 2"""
        cache = self.deleted_cache.get(ctx.channel.id)
        error = self.bot.config.get_emoji("error")
        
        if not cache:
            return await ctx.send(f"{error} nothing to snipe.")
        try:
            msg = cache[-index]
        except IndexError:
            return await ctx.send(f"{error} index out of range.")

        content = msg.content if msg.content else "*[no text]*"
        attach = self._format_attachments(msg)
        
        text = f"**sniped {msg.author.name}** (deleted)\n```\n{content}\n```{attach}"
        await ctx.send(text)

    @commands.command()
    async def editsnipe(self, ctx, index: int = 1):
        """snipes an edited message. usage: .editsnipe"""
        cache = self.edited_cache.get(ctx.channel.id)
        error = self.bot.config.get_emoji("error")
        
        if not cache:
            return await ctx.send(f"{error} nothing to editsnipe.")
        try:
            msg = cache[-index]
        except IndexError:
            return await ctx.send(f"{error} index out of range.")

        text = f"**editsniped {msg.author.name}** (original message)\n```\n{msg.content}\n```"
        await ctx.send(text)

    @commands.command()
    async def reactionsnipe(self, ctx, index: int = 1):
        """snipes a removed reaction. usage: .reactionsnipe"""
        cache = self.reaction_cache.get(ctx.channel.id)
        error = self.bot.config.get_emoji("error")
        
        if not cache:
            return await ctx.send(f"{error} nothing to reactionsnipe.")
        try:
            msg = cache[-index]
        except IndexError:
            return await ctx.send(f"{error} index out of range.")

        text = f"**reaction sniped from {msg.author.name}**\n```\n{msg.content}\n```"
        await ctx.send(text)

async def setup(bot):
    await bot.add_cog(Sniper(bot))
