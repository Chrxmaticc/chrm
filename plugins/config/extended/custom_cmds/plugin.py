import discord
from discord.ext import commands

class CustomCommandsMixin:
    """Commands for this sub-cog; assembled into the package cog."""
    @commands.Cog.listener()
    async def on_message_customs(self, message):
        # We only want to trigger this for our own messages
        if message.author.id != self.bot.user.id or not message.guild:
            return

        # Get the prefix
        prefixes = self.bot.command_prefix
        if isinstance(prefixes, str): prefixes = [prefixes]
        
        used_prefix = next((p for p in prefixes if message.content.startswith(p)), None)
        if not used_prefix:
            return

        # Extract the command name
        content = message.content[len(used_prefix):].strip()
        cmd_name = content.split(" ")[0].lower()
        
        custom_cmds = self.bot.config.data["features"]["custom_commands"]
        
        # If the command matches a custom command, fire it!
        if cmd_name in custom_cmds:
            response = custom_cmds[cmd_name]
            
            # Replace variables
            # {user} = the person who sent the message
            # {channel} = the channel name
            response = response.replace("{user}", message.author.mention)
            response = response.replace("{channel}", message.channel.mention)
            response = response.replace("{server}", message.guild.name)
            
            # Wait for the human delay before sending
            await self.bot.human_delay()
            await message.channel.send(response)

    @commands.command()
    async def addcmd(self, ctx, trigger: str, *, response: str):
        """adds a custom command. usage: .addcmd <trigger> <response>"""
        trigger = trigger.lower()
        error = self.bot.config.get_emoji("error")
        success = self.bot.config.get_emoji("success")

        # Prevent overwriting real commands
        if self.bot.get_command(trigger):
            return await ctx.send(f"{error} `{trigger}` is already a built-in command.")

        self.bot.config.data["features"]["custom_commands"][trigger] = response
        await ctx.send(f"{success} custom command `{trigger}` created!")

    @commands.command()
    async def delcmd(self, ctx, trigger: str):
        """deletes a custom command. usage: .delcmd <trigger>"""
        trigger = trigger.lower()
        error = self.bot.config.get_emoji("error")
        success = self.bot.config.get_emoji("success")

        if trigger in self.bot.config.data["features"]["custom_commands"]:
            del self.bot.config.data["features"]["custom_commands"][trigger]
            await ctx.send(f"{success} deleted custom command `{trigger}`.")
        else:
            await ctx.send(f"{error} custom command `{trigger}` doesn't exist.")

    @commands.command()
    async def listcmds(self, ctx):
        """lists all your custom commands"""
        custom_cmds = self.bot.config.data["features"]["custom_commands"]
        if not custom_cmds:
            return await ctx.send("you have no custom commands.")
            
        text = "**your custom commands:**\n"
        for trigger, resp in custom_cmds.items():
            text += f"`{trigger}` ➔ {resp}\n"
            
        await ctx.send(text)
