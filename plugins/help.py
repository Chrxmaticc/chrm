import discord
from discord.ext import commands

class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="help")
    async def help_command(self, ctx):
        prefix = self.bot.command_prefix
        
        embed = discord.Embed(
            title="chrm selfbot commands",
            description=f"prefix: `{prefix}` | all commands are lowercase",
            color=0x2b2d31
        )
        
        embed.add_field(
            name="automation",
            value=(
                f"`{prefix}addrespond <trigger> <response>`\n"
                f"`{prefix}addreact <trigger> <emoji>`\n"
                f"`{prefix}afk <message>`\n"
                f"`{prefix}unafk`\n"
                f"`{prefix}delay <seconds>`\n"
                f"`{prefix}toggledelay`\n"
                f"`{prefix}prefix <new_prefix>`"
            ),
            inline=False
        )
        
        embed.add_field(
            name="utility",
            value=(
                f"`{prefix}purge <amount>`\n"
                f"`{prefix}blacktea`\n"
                f"`{prefix}snipe`"
            ),
            inline=False
        )
        
        embed.add_field(
            name="presence",
            value=(
                f"`{prefix}rpc <playing/watching/listening> <text>`\n"
                f"`{prefix}stream <url> <text>`\n"
                f"`{prefix}customstatus <text>`\n"
                f"`{prefix}clearstatus`"
            ),
            inline=False
        )
        
        embed.add_field(
            name="music",
            value=(
                f"`{prefix}lyrics <song name>`\n"
                f"`{prefix}stoplyrics`"
            ),
            inline=False
        )
        
        embed.add_field(
            name="ai",
            value=(
                f"`{prefix}ai <prompt>`\n"
                f"`{prefix}image <prompt>`"
            ),
            inline=False
        )

        embed.set_footer(text="chrm on top.")
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Help(bot))
