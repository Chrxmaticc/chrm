import discord
from discord.ext import commands
import random

from core import api

class RespondersMixin:
    """Commands for this sub-cog; assembled into the package cog."""
    async def _save_feature(self, feature_key, data):
        await api.save_feature(self.bot, feature_key, data, tag="AUTOMATION")

    @commands.Cog.listener()
    async def on_message_responders(self, message):
        if message.author.id == self.bot.user.id or not message.content:
            return

        content_lower = message.content.lower()
        features = self.bot.config.data.get("features", {})

        # --- AFK CHECK ---
        afk = features.get("afk", {})
        if afk.get("enabled") and self.bot.user.mentioned_in(message):
            await self.bot.human_delay()
            return await message.reply(afk.get("message", "afk"), mention_author=True)

        # --- AUTORESPOND CHECK ---
        autorespond = features.get("autorespond", {})
        for trigger, config in autorespond.items():
            if trigger.lower() in content_lower:
                
                # Check Scope first
                scope = config.get("scope", "all") if isinstance(config, dict) else "all"
                if scope == "dm" and message.guild is not None:
                    continue # Skip if it's a server but we only want DMs
                if scope == "channel" and message.channel.id != config.get("channel_id"):
                    continue # Skip if it's a different channel

                await self.bot.human_delay()
                
                if isinstance(config, str):
                    response_text = config
                    is_reply = False
                else:
                    responses = config.get("responses", [])
                    is_reply = config.get("reply", False)
                    response_text = random.choice(responses) if responses else ""
                
                if not response_text: continue

                if is_reply:
                    await message.reply(response_text)
                else:
                    await message.channel.send(response_text)
                break

        # --- AUTOREACT CHECK ---
        autoreact = features.get("autoreact", {})
        for trigger, config in autoreact.items():
            if trigger.lower() in content_lower:
                
                # Check Scope
                scope = config.get("scope", "all") if isinstance(config, dict) else "all"
                if scope == "dm" and message.guild is not None:
                    continue
                if scope == "channel" and message.channel.id != config.get("channel_id"):
                    continue

                await self.bot.human_delay()
                emojis_str = config.get("emojis", "") if isinstance(config, dict) else config
                
                for emoji in emojis_str.split(","):
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
        error = self.bot.config.get_emoji("error")
        await ctx.send(f"{error} usage: `.responder add [dm/channel] <trigger> <response>`")

    @responder.command(name="add")
    async def responder_add(self, ctx, trigger: str, *, response: str):
        """
        usage: 
        .responder add hello hi
        .responder add dm hello hi
        .responder add channel reply hello hi
        """
        scope = "all"
        channel_id = None
        is_reply = False

        # 1. Parse Scope
        if trigger.lower() == "dm":
            scope = "dm"
            parts = response.split(" ", 1)
            if len(parts) < 2: return await ctx.send("format: `.responder add dm <trigger> <response>`")
            trigger, response = parts[0], parts[1]
        elif trigger.lower() == "channel":
            scope = "channel"
            channel_id = ctx.channel.id
            parts = response.split(" ", 1)
            if len(parts) < 2: return await ctx.send("format: `.responder add channel <trigger> <response>`")
            trigger, response = parts[0], parts[1]

        # 2. Parse Reply
        if trigger.lower() == "reply":
            is_reply = True
            parts = response.split(" ", 1)
            if len(parts) < 2: return await ctx.send("format: ...reply <trigger> <response>")
            trigger, response = parts[0], parts[1]

        # Check for image attachments via reply
        attachment_url = ""
        if ctx.message.reference and ctx.message.reference.resolved:
            if ctx.message.reference.resolved.attachments:
                attachment_url = f" {ctx.message.reference.resolved.attachments[0].url}"

        responses = [r.strip() + attachment_url for r in response.split("||") if r.strip()]

        autorespond = self.bot.config.data.get("features", {}).get("autorespond", {})
        autorespond[trigger.lower()] = {
            "responses": responses,
            "reply": is_reply,
            "scope": scope,
            "channel_id": channel_id
        }
        await self._save_feature("autorespond", autorespond)

        emoji = self.bot.config.get_emoji("success")
        scope_text = "in DMs" if scope == "dm" else ("in this channel" if scope == "channel" else "everywhere")
        mode = "reply" if is_reply else "send"
        await ctx.send(f"{emoji} will {mode} to `{trigger.lower()}` {scope_text}")

    @responder.command(name="remove", aliases=["delete", "del"])
    async def responder_remove(self, ctx, trigger: str):
        autorespond = self.bot.config.data.get("features", {}).get("autorespond", {})
        if trigger.lower() in autorespond:
            del autorespond[trigger.lower()]
            await self._save_feature("autorespond", autorespond)
            await ctx.send(f"{self.bot.config.get_emoji('success')} removed `{trigger.lower()}`")
        else:
            await ctx.send(f"{self.bot.config.get_emoji('error')} trigger not found.")

    @responder.command(name="list")
    async def responder_list(self, ctx):
        autorespond = self.bot.config.data.get("features", {}).get("autorespond", {}) or {}
        if not autorespond:
            return await ctx.send("no auto-responders set yet.")

        lines = []
        for trigger, config in sorted(autorespond.items()):
            if isinstance(config, str):
                lines.append(f"`{trigger}` ➔ {config}")
            else:
                scope = f"[{config.get('scope', 'all').upper()}] " if config.get('scope') != 'all' else ""
                mode = "[REPLY] " if config.get("reply") else ""
                resp_str = " | ".join(config.get("responses", []))
                lines.append(f"`{trigger}` ➔ {scope}{mode}{resp_str}")
                
        await ctx.send("**active auto-responders:**\n" + "\n".join(lines))

    # ==========================================
    # REACTION GROUP
    # ==========================================
    @commands.group(name="reaction", aliases=["react"], invoke_without_command=True)
    async def reaction(self, ctx):
        await ctx.send(f"{self.bot.config.get_emoji('error')} usage: `.reaction add [dm/channel] <trigger> <emoji>`")

    @reaction.command(name="add")
    async def reaction_add(self, ctx, trigger: str, emoji: str):
        scope = "all"
        channel_id = None

        if trigger.lower() == "dm":
            scope = "dm"
            parts = emoji.split(" ", 1)
            if len(parts) < 2: return await ctx.send("format: `.reaction add dm <trigger> <emoji>`")
            trigger, emoji = parts[0], parts[1]
        elif trigger.lower() == "channel":
            scope = "channel"
            channel_id = ctx.channel.id
            parts = emoji.split(" ", 1)
            if len(parts) < 2: return await ctx.send("format: `.reaction add channel <trigger> <emoji>`")
            trigger, emoji = parts[0], parts[1]

        autoreact = self.bot.config.data.get("features", {}).get("autoreact", {})
        autoreact[trigger.lower()] = {
            "emojis": emoji,
            "scope": scope,
            "channel_id": channel_id
        }
        await self._save_feature("autoreact", autoreact)

        scope_text = "in DMs" if scope == "dm" else ("in this channel" if scope == "channel" else "everywhere")
        await ctx.send(f"{self.bot.config.get_emoji('success')} will react to `{trigger.lower()}` {scope_text} with {emoji}")

    @reaction.command(name="remove", aliases=["delete", "del"])
    async def reaction_remove(self, ctx, trigger: str):
        autoreact = self.bot.config.data.get("features", {}).get("autoreact", {})
        if trigger.lower() in autoreact:
            del autoreact[trigger.lower()]
            await self._save_feature("autoreact", autoreact)
            await ctx.send(f"{self.bot.config.get_emoji('success')} removed `{trigger.lower()}`")
        else:
            await ctx.send(f"{self.bot.config.get_emoji('error')} trigger not found.")

    # ==========================================
    # AFK
    # ==========================================
    @commands.command()
    async def afk(self, ctx, *, msg="afk"):
        await self._save_feature("afk", {"enabled": True, "message": msg})
        await ctx.send(f"{self.bot.config.get_emoji('success')} afk enabled: {msg}")

    @commands.command()
    async def unafk(self, ctx):
        await self._save_feature("afk", {"enabled": False, "message": "afk"})
        await ctx.send(f"{self.bot.config.get_emoji('success')} afk disabled.")
