import discord
from discord.ext import commands
import asyncio
import re

class NicknameRotator(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.nick_task = None

    @commands.command()
    async def namerotator(self, ctx, *, args):
        """rotates your nickname. usage: .namerotator name1, name2, name3 5h"""
        # Regex to find the time at the end (e.g., 5h, 30m, 10s)
        time_match = re.search(r'(\d+)([smh])$', args)
        if not time_match:
            error = self.bot.config.get_emoji("error")
            return await ctx.send(f"{error} missing time. usage: `.namerotator name1, name2 5h`")

        amount = int(time_match.group(1))
        unit = time_match.group(2)
        
        # Calculate seconds
        multiplier = {'s': 1, 'm': 60, 'h': 3600}
        total_seconds = amount * multiplier[unit]

        # Extract the names string and split by comma
        names_string = args[:time_match.start()].strip()
        names = [name.strip() for name in names_string.split(',') if name.strip()]

        if not names:
            error = self.bot.config.get_emoji("error")
            return await ctx.send(f"{error} no names provided.")

        if self.nick_task and not self.nick_task.done():
            self.nick_task.cancel()

        self.nick_task = asyncio.create_task(self._rotate_nick(ctx.guild, names, total_seconds))
        
        success = self.bot.config.get_emoji("success")
        await ctx.send(f"{success} nickname rotator started. cycling {len(names)} names every {amount}{unit}.")

    async def _rotate_nick(self, guild, names, interval):
        try:
            index = 0
            while True:
                new_nick = names[index % len(names)]
                try:
                    # Only change nickname in the current guild to avoid mass rate limits
                    if guild and guild.me.guild_permissions.change_nickname:
                        await guild.me.edit(nick=new_nick)
                        print(f"[nickrotator] changed nick to {new_nick}")
                except Exception as e:
                    print(f"failed to change nick: {e}")
                
                index += 1
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            pass

    @commands.command()
    async def stopname(self, ctx):
        if self.nick_task and not self.nick_task.done():
            self.nick_task.cancel()
            success = self.bot.config.get_emoji("success")
            await ctx.send(f"{success} nickname rotator stopped.")
        else:
            error = self.bot.config.get_emoji("error")
            await ctx.send(f"{error} rotator is not running.")

async def setup(bot):
    await bot.add_cog(NicknameRotator(bot))
