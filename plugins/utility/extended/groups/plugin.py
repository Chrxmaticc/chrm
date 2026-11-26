import discord
from discord.ext import commands
import asyncio
import random

from core import api

class GroupChatMixin:
    """Commands for this sub-cog; assembled into the package cog."""
    async def _save_feature(self, feature_key, data):
        await api.save_feature(self.bot, feature_key, data, tag="GC")

    def is_gc(ctx):
        if not isinstance(ctx.channel, discord.GroupChannel):
            raise commands.CheckFailure("This command can only be used in a Group Chat.")
        return True

    # ==========================================
    # NAME CHANGERS
    # ==========================================
    @commands.command()
    @commands.check(is_gc)
    async def gcname(self, ctx, *, name: str):
        """changes the group chat name. usage: .gcname new name"""
        try:
            await ctx.channel.edit(name=name)
            await ctx.message.delete()
        except Exception as e:
            await ctx.send(f"{self.bot.config.get_emoji('error')} failed: {e}")

    @commands.command()
    @commands.check(is_gc)
    @commands.cooldown(1, 60, commands.BucketType.channel) # 1 min cooldown
    async def spamname(self, ctx, count: int, *, name: str):
        """spams the gc name. usage: .spamname 5 new name"""
        if count > 15:
            return await ctx.send(f"{self.bot.config.get_emoji('error')} max is 15 to prevent rate limits.")
            
        await ctx.message.delete()
        loading = await ctx.send(f"{self.bot.config.get_emoji('loading')} spamming name {count} times...")
        
        for i in range(count):
            try:
                await ctx.channel.edit(name=name)
                await asyncio.sleep(random.uniform(2.5, 4.0)) # Safe delay
            except Exception as e:
                print(f"[GC] Spamname error: {e}")
                break
                
        await loading.delete()

    # ==========================================
    # MEMBER MANAGEMENT
    # ==========================================
    @commands.command()
    @commands.check(is_gc)
    async def gcadd(self, ctx, *users: discord.User):
        """adds users to the gc. usage: .gcadd @user1 @user2"""
        if not users:
            return await ctx.send(f"{self.bot.config.get_emoji('error')} mention users to add.")
        try:
            await ctx.channel.add_recipients(*users)
            await ctx.message.delete()
        except Exception as e:
            await ctx.send(f"{self.bot.config.get_emoji('error')} failed to add: {e}")

    @commands.command()
    @commands.check(is_gc)
    async def gcremove(self, ctx, user: discord.User):
        """removes a user from the gc. usage: .gcremove @user"""
        try:
            await ctx.channel.remove_recipients(user)
            await ctx.message.delete()
        except Exception as e:
            await ctx.send(f"{self.bot.config.get_emoji('error')} failed to remove: {e}")

    @commands.command()
    @commands.check(is_gc)
    async def gclist(self, ctx):
        """lists everyone in the gc."""
        users = [f"- {u.name}" for u in ctx.channel.recipients]
        msg = f"**Members ({len(users)+1}):**\n" + "\n".join(users) + f"\n- {self.bot.user.name} (You)"
        await ctx.send(msg)

    @commands.command()
    @commands.check(is_gc)
    async def gcnuke(self, ctx):
        """removes everyone from the gc (must be owner)."""
        if ctx.channel.owner_id != self.bot.user.id:
            return await ctx.send(f"{self.bot.config.get_emoji('error')} you must be the owner to nuke the gc.")
        
        await ctx.send(f"{self.bot.config.get_emoji('loading')} nuking gc...")
        for user in list(ctx.channel.recipients):
            try:
                await ctx.channel.remove_recipients(user)
                await asyncio.sleep(1.5) # Safe delay
            except:
                pass
        await ctx.send(f"{self.bot.config.get_emoji('success')} gc nuked.")

    @commands.command()
    @commands.check(is_gc)
    async def gcleave(self, ctx):
        """leaves the group chat."""
        await ctx.message.delete()
        await ctx.channel.leave()

    # ==========================================
    # AUTOMATION (AUTOLEAVE / AUTOADD)
    # ==========================================
    @commands.command()
    async def autoleave(self, ctx):
        """toggles automatically leaving servers/gcs when invited."""
        current = self.bot.config.data.get("features", {}).get("autoleave", False)
        new_state = not current
        await self._save_feature("autoleave", new_state)
        
        emoji = self.bot.config.get_emoji("success")
        await ctx.send(f"{emoji} autoleave is now **{'ON' if new_state else 'OFF'}**.")

    @commands.command()
    async def autoadd(self, ctx, *, query: str):
        """toggles auto-adding a user to any GC you join. usage: .autoadd @user | list | clear"""
        token = (query or "").strip().lower()
        stored = self.bot.config.data.get("features", {}).get("autoadd_users", [])
        current = stored if isinstance(stored, list) else []
        emoji = self.bot.config.get_emoji("success")

        if token in ("list", "ls", "show"):
            if not current:
                return await ctx.send(f"{emoji} nobody is on the autoadd list.")
            lines = ["### autoadd"]
            for uid in current:
                label = f"`{uid}`"
                try:
                    getter = getattr(self.bot, "get_user", None)
                    found = getter(int(uid)) if callable(getter) else None
                    if found is None:
                        found = await self.bot.fetch_user(int(uid))
                    label = f"{getattr(found, 'name', uid)} · {label}"
                except Exception:
                    pass
                lines.append(f"- {label}")
            lines.append("-# `.autoadd <user>` toggles one · `.autoadd clear` empties it")
            return await ctx.send("\n".join(lines))

        if token in ("clear", "reset", "all", "off", "none"):
            if not current:
                return await ctx.send(f"{emoji} the autoadd list is already empty.")
            self.bot.config.data.setdefault("features", {})["autoadd_users"] = []
            await self._save_feature("autoadd_users", [])
            return await ctx.send(
                f"{emoji} autoadd is off — nobody gets added to new group chats."
            )

        user = None
        try:
            user = await commands.UserConverter().convert(ctx, query)
        except:
            pass
        
        if not user:
            return await ctx.send(f"{self.bot.config.get_emoji('error')} user not found. use mention or id.")

        autoadd_users = current

        if user.id in autoadd_users:
            autoadd_users.remove(user.id)
            state = "OFF"
        else:
            autoadd_users.append(user.id)
            state = "ON"
            
        await self._save_feature("autoadd_users", autoadd_users)
        await ctx.send(f"{self.bot.config.get_emoji('success')} autoadd for **{user.name}** is now **{state}**.")

    # ==========================================
    # LISTENERS
    # ==========================================
    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        if self.bot.config.data.get("features", {}).get("autoleave", False):
            print(f"[GC] Auto-leaving server: {guild.name}")
            await guild.leave()

    @commands.Cog.listener()
    async def on_private_channel_create(self, channel):
        if not isinstance(channel, discord.GroupChannel):
            return

        # 1. Autoleave (only if we didn't create the GC)
        if channel.owner_id != self.bot.user.id:
            if self.bot.config.data.get("features", {}).get("autoleave", False):
                print(f"[GC] Auto-leaving GC: {channel.id}")
                await channel.leave()
                return

        # 2. Autoadd
        autoadd_ids = self.bot.config.data.get("features", {}).get("autoadd_users", [])
        if autoadd_ids:
            users_to_add = []
            for uid in autoadd_ids:
                try:
                    u = self.bot.get_user(uid) or await self.bot.fetch_user(uid)
                    if u and u not in channel.recipients and u.id != self.bot.user.id:
                        users_to_add.append(u)
                except:
                    pass
            
            if users_to_add:
                try:
                    await channel.add_recipients(*users_to_add)
                    print(f"[GC] Auto-added {len(users_to_add)} users to {channel.id}")
                except Exception as e:
                    print(f"[GC] Autoadd error: {e}")
