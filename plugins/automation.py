import discord
from discord.ext import commands

class Automation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.id == self.bot.user.id or not message.guild:
            return

        features = self.bot.config.get_feature("afk")
        if features and features.get("enabled"):
            if self.bot.user.mentioned_in(message):
                await self.bot.human_delay()
                await message.reply(features["message"], mention_author=True)
                return

        content_lower = message.content.lower()
        
        ar = self.bot.config.get_feature("autorespond") or {}
        for trigger, response in ar.items():
            if trigger.lower() in content_lower:
                await self.bot.human_delay()
                await message.channel.send(response.lower())
                break

        arx = self.bot.config.get_feature("autoreact") or {}
        for trigger, emoji in arx.items():
            if trigger.lower() in content_lower:
                await self.bot.human_delay()
                try:
                    await message.add_reaction(emoji)
                except:
                    pass
                break

    @commands.command()
    async def toggledelay(self, ctx):
        current = self.bot.config.data["settings"].get("delays_enabled", True)
        self.bot.config.data["settings"]["delays_enabled"] = not current
        emoji = self.bot.config.get_emoji("success")
        await ctx.send(f"{emoji} delays are now **{'on' if not current else 'off'}**")

    @commands.command()
    async def afk(self, ctx, *, msg="<:chrm_afk:1234567890> i am currently afk."):
        self.bot.config.data["features"]["afk"] = {"enabled": True, "message": msg.lower()}
        emoji = self.bot.config.get_emoji("success")
        await ctx.send(f"{emoji} afk enabled.")

    @commands.command()
    async def unafk(self, ctx):
        self.bot.config.data["features"]["afk"]["enabled"] = False
        emoji = self.bot.config.get_emoji("success")
        await ctx.send(f"{emoji} welcome back. afk disabled.")

    @commands.command()
    async def addrespond(self, ctx, trigger, *, response):
        self.bot.config.data["features"]["autorespond"][trigger] = response.lower()
        emoji = self.bot.config.get_emoji("success")
        await ctx.send(f"{emoji} will respond to '{trigger.lower()}'")

    @commands.command()
    async def addreact(self, ctx, trigger, emoji):
        self.bot.config.data["features"]["autoreact"][trigger] = emoji
        success = self.bot.config.get_emoji("success")
        await ctx.send(f"{success} will react to '{trigger.lower()}'")

async def setup(bot):
    await bot.add_cog(Automation(bot))
