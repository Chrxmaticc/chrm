import discord
from discord.ext import commands

class Aliases(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.processed_messages = set()

    @commands.Cog.listener()
    async def on_message(self, message):
        # Prevent infinite loops
        if message.id in self.processed_messages:
            return
        if message.author.id != self.bot.user.id or not message.content:
            return

        # Ensure aliases dict exists
        if "features" not in self.bot.config.data:
            self.bot.config.data["features"] = {}
        if "aliases" not in self.bot.config.data["features"]:
            self.bot.config.data["features"]["aliases"] = {}

        aliases = self.bot.config.data["features"]["aliases"]

        # Get the prefix being used
        prefixes = self.bot.command_prefix
        if isinstance(prefixes, str): prefixes = [prefixes]
        
        used_prefix = next((p for p in prefixes if message.content.startswith(p)), None)
        if not used_prefix:
            return

        # Split into command and arguments
        parts = message.content[len(used_prefix):].strip().split(" ", 1)
        cmd_name = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        # If the typed command is an alias, rewrite the message and process it
        if cmd_name in aliases:
            target_cmd = aliases[cmd_name]
            message.content = f"{used_prefix}{target_cmd} {args}".strip()
            self.processed_messages.add(message.id)
            await self.bot.process_commands(message)

    @commands.group(invoke_without_command=True)
    async def alias(self, ctx):
        """manage command aliases. usage: .alias add <alias> <command>"""
        error = self.bot.config.get_emoji("error")
        await ctx.send(f"{error} usage: `.alias add <alias> <command>` or `.alias remove <alias>`")

    @alias.command(name="add")
    async def alias_add(self, ctx, shortcut: str, command: str):
        """adds an alias. usage: .alias add s snipe"""
        # Don't let them alias the alias command itself
        if command.lower() == "alias":
            return await ctx.send(f"{self.bot.config.get_emoji('error')} you can't alias the alias command.")

        self.bot.config.data["features"]["aliases"][shortcut.lower()] = command.lower()
        emoji = self.bot.config.get_emoji("success")
        await ctx.send(f"{emoji} now `{shortcut}` will run `{command}`")

    @alias.command(name="remove", aliases=["delete", "del"])
    async def alias_remove(self, ctx, shortcut: str):
        """removes an alias. usage: .alias remove s"""
        if shortcut.lower() in self.bot.config.data["features"]["aliases"]:
            del self.bot.config.data["features"]["aliases"][shortcut.lower()]
            emoji = self.bot.config.get_emoji("success")
            await ctx.send(f"{emoji} removed alias `{shortcut}`.")
        else:
            error = self.bot.config.get_emoji("error")
            await ctx.send(f"{error} alias `{shortcut}` doesn't exist.")

    @alias.command(name="list")
    async def alias_list(self, ctx):
        """lists all aliases"""
        aliases = self.bot.config.data["features"]["aliases"]
        if not aliases:
            return await ctx.send("no aliases created yet.")
            
        text = "**active aliases:**\n"
        for shortcut, cmd in aliases.items():
            text += f"`{shortcut}` ➔ `{cmd}`\n"
            
        await ctx.send(text)

async def setup(bot):
    await bot.add_cog(Aliases(bot))
