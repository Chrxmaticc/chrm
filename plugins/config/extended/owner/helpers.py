import discord
from discord.ext import commands
import os
import psutil

# Your Discord ID
OWNER_ID = 1527403360880431275

def is_owner():
    async def predicate(ctx):
        # Only allows the command if the invoker's ID matches yours
        return ctx.author.id == OWNER_ID
    return commands.check(predicate)
