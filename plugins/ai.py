import discord
from discord.ext import commands
import os
from openai import OpenAI

class AI(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    @commands.command()
    async def ai(self, ctx, *, prompt):
        loading = self.bot.config.get_emoji("loading")
        await ctx.message.edit(content=f"{loading} thinking...")
        try:
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=150
            )
            reply = response.choices[0].message.content.lower()
            await ctx.message.edit(content=reply)
        except Exception as e:
            error = self.bot.config.get_emoji("error")
            await ctx.message.edit(content=f"{error} ai error: {str(e).lower()}")

    @commands.command()
    async def image(self, ctx, *, prompt):
        loading = self.bot.config.get_emoji("loading")
        await ctx.message.edit(content=f"{loading} generating image...")
        try:
            response = self.client.images.generate(
                model="dall-e-2", 
                prompt=prompt,
                size="512x512",
                quality="standard",
                n=1,
            )
            image_url = response.data[0].url
            img_emoji = self.bot.config.get_emoji("image")
            await ctx.message.edit(content=f"{img_emoji} image: {image_url}")
        except Exception as e:
            error = self.bot.config.get_emoji("error")
            await ctx.message.edit(content=f"{error} image error: {str(e).lower()}")

async def setup(bot):
    await bot.add_cog(AI(bot))
