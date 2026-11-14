import discord
from discord.ext import commands

class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="help")
    async def help_command(self, ctx):
        prefix = self.bot.command_prefix
        if isinstance(prefix, list):
            prefix_str = prefix[0] # Just show the first prefix
        else:
            prefix_str = prefix

        embed = discord.Embed(
            title="chrm selfbot commands",
            description=f"main prefix: `{prefix_str}` | all commands lowercase",
            color=0x2b2d31
        )
        
        embed.add_field(
            name="automation",
            value=(
                f"`{prefix_str}addrespond <trigger> <response>`\n"
                f"`{prefix_str}addreact <trigger> <emoji>`\n"
                f"`{prefix_str}afk <message>` / `{prefix_str}unafk`\n"
                f"`{prefix_str}delay <seconds>` / `{prefix_str}toggledelay`\n"
                f"`{prefix_str}prefix` / `{prefix_str}addprefix` / `{prefix_str}removeprefix`"
            ),
            inline=False
        )
        
        embed.add_field(
            name="presence & rpc",
            value=(
                f"`{prefix_str}rpc <type> <name> | <details> | <state> | <large_img> | <small_img> | elapsed`\n"
                f"`{prefix_str}stream <url> <title>`\n"
                f"`{prefix_str}customstatus <text>`\n"
                f"`{prefix_str}clearstatus` - wipe rpc\n"
                f"`{prefix_str}togglerotator` / `{prefix_str}addstatus`"
            ),
            inline=False
        )
        
        embed.add_field(
            name="utility & sniping",
            value=(
                f"`{prefix_str}purge <amount>`\n"
                f"`{prefix_str}blacktea`\n"
                f"`{prefix_str}snipe` / `{prefix_str}editsnipe`\n"
                f"`{prefix_str}userinfo [@user]` / `{prefix_str}avatar [@user]`"
            ),
            inline=False
        )

        embed.add_field(
            name="music & games",
            value=(
                f"`{prefix_str}lyrics <song>` / `{prefix_str}stoplyrics`\n"
                f"`{prefix_str}fakeplay <game>` / `{prefix_str}stopfakeplay`\n"
                f"`{prefix_str}spotify <song> - <artist>` / `{prefix_str}stopspotify`"
            ),
            inline=False
        )

        embed.set_footer(text="chrm on top.")
        
        # FIXED: using embeds=[embed] instead of embed=embed
        await ctx.send(embeds=[embed])

async def setup(bot):
    await bot.add_cog(Help(bot))
