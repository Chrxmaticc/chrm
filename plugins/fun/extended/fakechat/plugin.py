import discord
from discord.ext import commands
import aiohttp
import urllib.parse

class FakeChatMixin:
    """Commands for this sub-cog; assembled into the package cog."""
    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def fakechat(self, ctx, *, args: str):
        """
        generates a fake discord message. 
        usage: .fakechat <text> [user=name] [theme=dark/light] [reactions=🔥] [mention_highlight=true]
        """
        loading = await ctx.send(f"{self.bot.config.get_emoji('loading')} generating fake chat...")
        
        # 1. Parse the arguments
        parts = args.split()
        text_parts = []
        params = {}
        
        # The valid keys from the API
        valid_keys = [
            "user", "theme", "display_font", "image", "timestamp", 
            "mention_highlight", "reactions", "togif", "use_username"
        ]
        
        for part in parts:
            if "=" in part:
                key, value = part.split("=", 1)
                if key.lower() in valid_keys:
                    params[key.lower()] = value
                    continue
            text_parts.append(part)
            
        text = " ".join(text_parts)
        
        if not text:
            await loading.delete()
            return await ctx.send(f"{self.bot.config.get_emoji('error')} you need to provide some text.")

        # 2. Set Defaults (Uses their Discord name and avatar if not specified)
        if "user" not in params:
            params["user"] = ctx.author.name
        if "image" not in params:
            params["image"] = ctx.author.display_avatar.url

        # 3. Build the URL
        base_url = "https://api.popcat.xyz/v2/fakechat"
        
        # Combine text and params into the query string
        query = {"text": text}
        query.update(params)
        
        # URL encode the entire query so spaces and emojis don't break the API
        url = f"{base_url}?{urllib.parse.urlencode(query)}"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        await loading.delete()
                        # Popcat returns a direct image URL, Discord will auto-embed it
                        await ctx.send(url) 
                    else:
                        await loading.edit(content=f"{self.bot.config.get_emoji('error')} api returned {resp.status}")
        except Exception as e:
            await loading.edit(content=f"{self.bot.config.get_emoji('error')} error: {e}")
