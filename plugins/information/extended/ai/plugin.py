import discord
from discord.ext import commands
import aiohttp

# Your exact system prompt
from .helpers import SYSTEM_PROMPT


class AIMixin:
    """Commands for this sub-cog; assembled into the package cog."""
    @commands.command()
    async def ai(self, ctx, *, prompt):
        """chat with chromed ai. usage: .ai hello"""
        loading = self.bot.config.get_emoji("loading")
        msg = await ctx.send(f"{loading} thinking...")

        # Kilo AI Gateway (Keyless/Free tier)
        url = "https://api.kilo.ai/api/gateway/chat/completions"
        
        payload = {
            "model": "kilo-auto/free", # Auto-router picks the best free model
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ]
        }

        # Headers for anonymous access (no API key needed)
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer anonymous",
            "X-KILOCODE-EDITORNAME": "chrm-selfbot"
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        reply = data["choices"][0]["message"]["content"]
                        reply = reply.lower().strip()
                        
                        # Handle discord 2000 char limit
                        if len(reply) > 1900:
                            reply = reply[:1900] + "..."
                            
                        await msg.edit(content=reply)
                    else:
                        error = self.bot.config.get_emoji("error")
                        error_text = await resp.text()
                        print(f"Kilo API Error {resp.status}: {error_text}")
                        await msg.edit(content=f"{error} api returned status {resp.status}")
        except Exception as e:
            error = self.bot.config.get_emoji("error")
            await msg.edit(content=f"{error} ai error: {str(e).lower()}")
