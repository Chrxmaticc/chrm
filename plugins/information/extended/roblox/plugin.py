import discord
from discord.ext import commands
import aiohttp
import random
import urllib.parse

class RobloxMixin:
    """Commands for this sub-cog; assembled into the package cog."""
    def get_insult(self, ctx):
        """25% chance to append the signature insult."""
        if random.random() < 0.25:
            return f"\n-# u prolly suck ass at roblox - owner of the sb."
        return ""

    async def resolve_user_id(self, query):
        """Resolves a username to a Roblox ID, or returns the ID if it's already a number."""
        if query.isdigit():
            return int(query)
        
        url = "https://users.roblox.com/v1/usernames/users"
        payload = {"usernames": [query], "excludeBannedUsers": True}
        
        async with aiohttp.ClientSession(headers=self.headers) as session:
            async with session.post(url, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data["data"]:
                        return data["data"][0]["id"]
        return None

    @commands.command()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def rblxuser(self, ctx, *, query: str):
        """gets roblox user info. usage: .rblxuser builderman"""
        loading = await ctx.send(f"{self.bot.config.get_emoji('loading')} scraping roblox...")
        uid = await self.resolve_user_id(query)
        
        if not uid:
            return await loading.edit(content=f"{self.bot.config.get_emoji('error')} user not found.")

        url = f"https://users.roblox.com/v1/users/{uid}"
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        return await loading.edit(content=f"{self.bot.config.get_emoji('error')} failed to fetch user info.")
                    data = await resp.json()
                    
            created_at = data.get("created", "Unknown").split("T")[0]
            desc = data.get("description", "No description.")
            if len(desc) > 150: desc = desc[:147] + "..."
            
            text = (
                f"**roblox user: {data['name']}**\n"
                f"**Display Name:** {data.get('displayName')}\n"
                f"**ID:** {data['id']}\n"
                f"**Created:** {created_at}\n"
                f"**Banned:** {data.get('isBanned', False)}\n"
                f"**Description:** {desc}\n"
                f"https://www.roblox.com/users/{data['id']}/profile"
            )
            text += self.get_insult(ctx)
            
            await loading.edit(content=text)
        except Exception as e:
            await loading.edit(content=f"{self.bot.config.get_emoji('error')} error: {e}")

    @commands.command()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def rblxavatar(self, ctx, *, query: str):
        """gets a roblox full body avatar. usage: .rblxavatar builderman"""
        loading = await ctx.send(f"{self.bot.config.get_emoji('loading')} fetching avatar...")
        uid = await self.resolve_user_id(query)
        
        if not uid:
            return await loading.edit(content=f"{self.bot.config.get_emoji('error')} user not found.")

        url = f"https://thumbnails.roblox.com/v1/users/avatar?userIds={uid}&size=420x420&format=Png&isCircular=false"
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(url) as resp:
                    data = await resp.json()
                    if resp.status == 200 and data["data"]:
                        img_url = data["data"][0].get("imageUrl")
                        if img_url:
                            insult = self.get_insult(ctx)
                            await loading.delete()
                            await ctx.send(f"**{query}'s avatar:**\n{img_url}{insult}")
                            return
            
            await loading.edit(content=f"{self.bot.config.get_emoji('error')} failed to fetch avatar.")
        except Exception as e:
            await loading.edit(content=f"{self.bot.config.get_emoji('error')} error: {e}")

    @commands.command()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def rblxheadshot(self, ctx, *, query: str):
        """gets a roblox headshot. usage: .rblxheadshot builderman"""
        loading = await ctx.send(f"{self.bot.config.get_emoji('loading')} fetching headshot...")
        uid = await self.resolve_user_id(query)
        
        if not uid:
            return await loading.edit(content=f"{self.bot.config.get_emoji('error')} user not found.")

        url = f"https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={uid}&size=420x420&format=Png&isCircular=false"
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(url) as resp:
                    data = await resp.json()
                    if resp.status == 200 and data["data"]:
                        img_url = data["data"][0].get("imageUrl")
                        if img_url:
                            insult = self.get_insult(ctx)
                            await loading.delete()
                            await ctx.send(f"**{query}'s headshot:**\n{img_url}{insult}")
                            return
            
            await loading.edit(content=f"{self.bot.config.get_emoji('error')} failed to fetch headshot.")
        except Exception as e:
            await loading.edit(content=f"{self.bot.config.get_emoji('error')} error: {e}")

    @commands.command()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def rblxgroups(self, ctx, *, query: str):
        """gets a roblox user's groups. usage: .rblxgroups builderman"""
        loading = await ctx.send(f"{self.bot.config.get_emoji('loading')} fetching groups...")
        uid = await self.resolve_user_id(query)
        
        if not uid:
            return await loading.edit(content=f"{self.bot.config.get_emoji('error')} user not found.")

        url = f"https://groups.roblox.com/v1/users/{uid}/groups/roles"
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        return await loading.edit(content=f"{self.bot.config.get_emoji('error')} failed to fetch groups.")
                    data = await resp.json()
                    
            groups = data.get("data", [])
            if not groups:
                return await loading.edit(content=f"{query} is not in any groups.{self.get_insult(ctx)}")

            text = f"**groups for {query} ({len(groups)}):**\n"
            for g in groups[:5]: # Show top 5
                text += f"- **{g['group']['name']}** | Rank: {g['role']['name']}\n"
            
            if len(groups) > 5:
                text += f"...and {len(groups)-5} more."
            
            text += self.get_insult(ctx)
            await loading.edit(content=text)
        except Exception as e:
            await loading.edit(content=f"{self.bot.config.get_emoji('error')} error: {e}")
