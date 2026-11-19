import discord
from discord.ext import commands
import os
import aiohttp
import random

from api_base import BASE_API

class Automation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _save_feature(self, feature_key, data):
        """Updates memory AND saves to the database so the sync loop doesn't wipe it."""
        if "features" not in self.bot.config.data:
            self.bot.config.data["features"] = {}
        
        self.bot.config.data["features"][feature_key] = data

        base_api = BASE_API
        try:
            async with aiohttp.ClientSession() as session:
                payload = {"settings": {"features": self.bot.config.data["features"]}}
                await session.patch(f"{base_api}/api/user/{self.bot.user_id}", json=payload)
        except Exception as e:
            print(f"[AUTOMATION] Failed to save to API: {e}")

    @commands.Cog.listener()
    async def on_message(self, message):
        # Ignore our own messages
        if message.author.id == self.bot.user.id or not message.content:
            return

        content_lower = message.content.lower()

        # --- AFK CHECK ---
        afk = self.bot.config.data.get("features", {}).get("afk", {})
        if afk.get("enabled") and self.bot.user.mentioned_in(message):
            await self.bot.human_delay()
            return await message.reply(afk.get("message", "afk"), mention_author=True)

        # --- AUTORESPOND CHECK ---
        autorespond = self.bot.config.data.get("features", {}).get("autorespond", {})
        for trigger, config in autorespond.items():
            if trigger.lower() in content_lower:
                await self.bot.human_delay()
                
                # Check if it's Voby's old string format OR the new dict format
                if isinstance(config, str):
                    response_text = config
                    is_reply = False
                else:
                    responses = config.get("responses", [])
                    is_reply = config.get("reply", False)
                    # Randomize ONLY if there are multiple options
                    response_text = random.choice(responses) if responses else ""
                
                if not response_text: continue

                if is_reply:
                    await message.reply(response_text)
                else:
                    await message.channel.send(response_text)
                break # Stop checking other triggers once one fires

        # --- AUTOREACT CHECK ---
        autoreact = self.bot.config.data.get("features", {}).get("autoreact", {})
        for trigger, emojis in autoreact.items():
            if trigger.lower() in content_lower:
                await self.bot.human_delay()
                # Split by comma to support multiple reactions
                for emoji in emojis.split(","):
                    try:
                        await message.add_reaction(emoji.strip())
                    except Exception as e:
                        print(f"[AUTOMATION] Failed to react: {e}")
                break

    # ==========================================
    # RESPONDER GROUP
    # ==========================================
    @commands.group(name="responder", aliases=["respond"], invoke_without_command=True)
    async def responder(self, ctx):
        """manages auto-responders. usage: .responder add <trigger> <response>"""
        error = self.bot.config.get_emoji("error")
        await ctx.send(
            f"{error} usage: `.responder add <trigger> <response>` | "
            f"`.responder remove <trigger>` | `.responder list`"
        )

    @responder.command(name="add")
    async def responder_add(self, ctx, trigger: str, *, response: str):
        """
        adds an auto-responder. 
        usage: .responder add hello hi
        for reply: .responder add reply hello hi
        for random: .responder add hello hi || yo || sup
        """
        is_reply = False
        if trigger.lower() == "reply":
            parts = response.split(" ", 1)
            if len(parts) < 2: 
                return await ctx.send("format: `.responder add reply <trigger> <response>`")
            trigger = parts[0]
            response = parts[1]
            is_reply = True

        # Check for image attachments via reply
        attachment_url = ""
        if ctx.message.reference and ctx.message.reference.resolved:
            if ctx.message.reference.resolved.attachments:
                attachment_url = f" {ctx.message.reference.resolved.attachments[0].url}"

        # Split by || for random responses
        responses = [r.strip() + attachment_url for r in response.split("||") if r.strip()]

        autorespond = self.bot.config.data.get("features", {}).get("autorespond", {})
        autorespond[trigger.lower()] = {
            "responses": responses,
            "reply": is_reply
        }
        await self._save_feature("autorespond", autorespond)

        emoji = self.bot.config.get_emoji("success")
        mode = "reply" if is_reply else "send"
        await ctx.send(f"{emoji} will now {mode} to `{trigger.lower()}`")

    @responder.command(name="edit")
    async def responder_edit(self, ctx, trigger: str, *, response: str):
        """edits an existing auto-responder"""
        autorespond = self.bot.config.data.get("features", {}).get("autorespond", {})
        if trigger.lower() not in autorespond:
            return await ctx.send(f"{self.bot.config.get_emoji('error')} `{trigger}` not found.")

        responses = [r.strip() for r in response.split("||") if r.strip()]
        
        # Keep original reply status if it exists
        if isinstance(autorespond[trigger.lower()], str):
            autorespond[trigger.lower()] = {"responses": responses, "reply": False}
        else:
            autorespond[trigger.lower()]["responses"] = responses
            
        await self._save_feature("autorespond", autorespond)
        await ctx.send(f"{self.bot.config.get_emoji('success')} updated response for `{trigger.lower()}`")

    @responder.command(name="remove", aliases=["delete", "del"])
    async def responder_remove(self, ctx, trigger: str):
        """removes an auto-responder. usage: .responder remove hello"""
        autorespond = self.bot.config.data.get("features", {}).get("autorespond", {})
        if trigger.lower() in autorespond:
            del autorespond[trigger.lower()]
            await self._save_feature("autorespond", autorespond)
            emoji = self.bot.config.get_emoji("success")
            await ctx.send(f"{emoji} removed auto-responder for `{trigger.lower()}`")
        else:
            error = self.bot.config.get_emoji("error")
            await ctx.send(f"{error} trigger `{trigger.lower()}` not found.")

    @responder.command(name="list")
    async def responder_list(self, ctx):
        """lists all auto-responders."""
        autorespond = self.bot.config.data.get("features", {}).get("autorespond", {}) or {}
        if not autorespond:
            return await ctx.send("no auto-responders set yet.")

        lines = []
        for trigger, config in sorted(autorespond.items()):
            if isinstance(config, str):
                lines.append(f"`{trigger}` ➔ {config}")
            else:
                mode = "[reply] " if config.get("reply") else ""
                resp_str = " | ".join(config.get("responses", []))
                lines.append(f"`{trigger}` ➔ {mode}{resp_str}")
                
        await ctx.send("**active auto-responders:**\n" + "\n".join(lines))

    # ==========================================
    # REACTION GROUP
    # ==========================================
    @commands.group(name="reaction", aliases=["react"], invoke_without_command=True)
    async def reaction(self, ctx):
        """manages auto-reactions."""
        error = self.bot.config.get_emoji("error")
        await ctx.send(
            f"{error} usage: `.reaction add <trigger> <emoji>` | "
            f"`.reaction remove <trigger>` | `.reaction list`"
        )

    @reaction.command(name="add")
    async def reaction_add(self, ctx, trigger: str, emoji: str):
        """adds an auto-reactor. usage: .reaction add lol 😂,🔥"""
        autoreact = self.bot.config.data.get("features", {}).get("autoreact", {})
        autoreact[trigger.lower()] = emoji
        await self._save_feature("autoreact", autoreact)

        success = self.bot.config.get_emoji("success")
        await ctx.send(f"{success} will now react to `{trigger.lower()}` with {emoji}")

    @reaction.command(name="edit")
    async def reaction_edit(self, ctx, trigger: str, emoji: str):
        """edits an existing auto-reactor"""
        autoreact = self.bot.config.data.get("features", {}).get("autoreact", {})
        if trigger.lower() not in autoreact:
            return await ctx.send(f"{self.bot.config.get_emoji('error')} `{trigger}` not found.")
            
        autoreact[trigger.lower()] = emoji
        await self._save_feature("autoreact", autoreact)
        await ctx.send(f"{self.bot.config.get_emoji('success')} updated reactions for `{trigger.lower()}`")

    @reaction.command(name="remove", aliases=["delete", "del"])
    async def reaction_remove(self, ctx, trigger: str):
        """removes an auto-reactor."""
        autoreact = self.bot.config.data.get("features", {}).get("autoreact", {})
        if trigger.lower() in autoreact:
            del autoreact[trigger.lower()]
            await self._save_feature("autoreact", autoreact)
            emoji = self.bot.config.get_emoji("success")
            await ctx.send(f"{emoji} removed auto-reactor for `{trigger.lower()}`")
        else:
            error = self.bot.config.get_emoji("error")
            await ctx.send(f"{error} trigger `{trigger.lower()}` not found.")

    @reaction.command(name="list")
    async def reaction_list(self, ctx):
        """lists all auto-reactions."""
        autoreact = self.bot.config.data.get("features", {}).get("autoreact", {}) or {}
        if not autoreact:
            return await ctx.send("no auto-reactions set yet.")

        lines = [f"`{trigger}` ➔ {emoji}" for trigger, emoji in sorted(autoreact.items())]
        await ctx.send("**active auto-reactions:**\n" + "\n".join(lines))

    # ==========================================
    # AFK
    # ==========================================
    @commands.command()
    async def afk(self, ctx, *, msg="afk"):
        """enable afk mode."""
        await self._save_feature("afk", {"enabled": True, "message": msg})
        emoji = self.bot.config.get_emoji("success")
        await ctx.send(f"{emoji} afk enabled: {msg}")

    @commands.command()
    async def unafk(self, ctx):
        """disable afk mode"""
        await self._save_feature("afk", {"enabled": False, "message": "afk"})
        emoji = self.bot.config.get_emoji("success")
        await ctx.send(f"{emoji} welcome back. afk disabled.")

async def setup(bot):
    await bot.add_cog(Automation(bot))
