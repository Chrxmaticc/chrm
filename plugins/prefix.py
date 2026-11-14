import discord
from discord.ext import commands

class PrefixManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def prefixes(self, ctx):
        """shows the current active prefixes"""
        prefixes = self.bot.config.data["settings"].get("prefixes", [".", ",", "?"])
        # format them nicely
        formatted = ", ".join([f"`{p}`" for p in prefixes])
        emoji = self.bot.config.get_emoji("success")
        await ctx.send(f"{emoji} current prefixes: {formatted}")

    @commands.command()
    async def addprefix(self, ctx, new_prefix: str):
        """adds a new prefix. usage: .addprefix !"""
        if len(new_prefix) > 5:
            error = self.bot.config.get_emoji("error")
            return await ctx.send(f"{error} prefix is too long (max 5 chars).")

        prefixes = self.bot.config.data["settings"].get("prefixes", [".", ",", "?"])
        
        if new_prefix in prefixes:
            error = self.bot.config.get_emoji("error")
            return await ctx.send(f"{error} prefix `{new_prefix}` is already active.")

        prefixes.append(new_prefix)
        self.bot.command_prefix = prefixes
        
        emoji = self.bot.config.get_emoji("success")
        await ctx.send(f"{emoji} added `{new_prefix}`. bot now responds to {', '.join([f'`{p}`' for p in prefixes])}")

    @commands.command()
    async def removeprefix(self, ctx, prefix_to_remove: str):
        """removes a prefix. usage: .removeprefix !"""
        if prefix_to_remove == ".":
            error = self.bot.config.get_emoji("error")
            return await ctx.send(f"{error} you cannot remove the `.` fallback prefix.")

        prefixes = self.bot.config.data["settings"].get("prefixes", [".", ",", "?"])
        
        if prefix_to_remove not in prefixes:
            error = self.bot.config.get_emoji("error")
            return await ctx.send(f"{error} prefix `{prefix_to_remove}` is not active.")

        prefixes.remove(prefix_to_remove)
        self.bot.command_prefix = prefixes
        
        emoji = self.bot.config.get_emoji("success")
        await ctx.send(f"{emoji} removed `{prefix_to_remove}`.")

    @commands.command()
    async def resetprefix(self, ctx):
        """resets all prefixes back to . , and ?"""
        default_prefixes = [".", ",", "?"]
        self.bot.config.data["settings"]["prefixes"] = default_prefixes
        self.bot.command_prefix = default_prefixes
        
        emoji = self.bot.config.get_emoji("success")
        await ctx.send(f"{emoji} prefixes reset to `.`, `,`, and `?`.")

async def setup(bot):
    await bot.add_cog(PrefixManager(bot))
