import discord
from discord.ext import commands

class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="help")
    async def help_command(self, ctx):
        prefix = self.bot.command_prefix
        if isinstance(prefix, list):
            prefix_str = prefix[0]
        else:
            prefix_str = prefix

        # Pure text formatting, no embeds
        help_text = (
            f"**chrm selfbot commands**\n"
            f"*prefix: `{prefix_str}` | all commands lowercase*\n\n"
            f"**automation**\n"
            f"`{prefix_str}addrespond <trigger> <response>`\n"
            f"`{prefix_str}addreact <trigger> <emoji>`\n"
            f"`{prefix_str}afk <message>` / `{prefix_str}unafk`\n"
            f"`{prefix_str}delay <seconds>` / `{prefix_str}toggledelay`\n"
            f"`{prefix_str}prefix` / `{prefix_str}addprefix` / `{prefix_str}removeprefix`\n\n"
            f"**presence & rpc**\n"
            f"`{prefix_str}rpc <type> <name> | <details> | <state> | <large_img> | <small_img> | elapsed`\n"
            f"`{prefix_str}stream <url> <title>`\n"
            f"`{prefix_str}customstatus <text>`\n"
            f"`{prefix_str}clearstatus` - wipe rpc\n"
            f"`{prefix_str}togglerotator` / `{prefix_str}addstatus`\n\n"
            f"**utility & sniping**\n"
            f"`{prefix_str}purge <amount>`\n"
            f"`{prefix_str}blacktea`\n"
            f"`{prefix_str}snipe` / `{prefix_str}editsnipe`\n"
            f"`{prefix_str}userinfo [@user]` / `{prefix_str}avatar [@user]`\n\n"
            f"**music & games**\n"
            f"`{prefix_str}lyrics <song>` / `{prefix_str}stoplyrics`\n"
            f"`{prefix_str}fakeplay <game>` / `{prefix_str}stopfakeplay`\n"
            f"`{prefix_str}spotify <song> - <artist>` / `{prefix_str}stopspotify`\n\n"
            f"*chrm on top.*"
        )
        
        await ctx.send(help_text)

async def setup(bot):
    await bot.add_cog(Help(bot))
