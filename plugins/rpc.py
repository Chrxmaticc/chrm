import discord
from discord.ext import commands
import asyncio
import re
from datetime import datetime
import hashlib
import json

# Helper to force external images into Discord's proxy format
def format_image_url(url):
    if not url:
        return None
    if url.startswith("mp:") or url.startswith("spotify:"):
        return url
    if "cdn.discordapp.com" in url or "media.discordapp.net" in url:
        return url.split("?")[0]
    if url.startswith("http"):
        url_hash = hashlib.md5(url.encode()).hexdigest()
        clean_url = url.replace("https://", "").replace("http://", "")
        return f"mp:external/{url_hash}/https/{clean_url}"
    return url

class RPC(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.custom_rotator_task = None

    def cog_unload(self):
        if self.custom_rotator_task and not self.custom_rotator_task.done():
            self.custom_rotator_task.cancel()

    # ==========================================
    # 1. V2 UI COMMAND
    # ==========================================
    @commands.command()
    async def rpcmenu(self, ctx):
        """opens the components v2 rpc manager"""
        payload = {
            "flags": 32768,
            "components": [
                {
                    "type": 17,
                    "accent_color": 0x2b2d31,
                    "components": [
                        {"type": 10, "content": "## RPC Manager\nManage your Rich Presence directly from this menu."},
                        {"type": 14, "divider": True, "spacing": 1},
                        {
                            "type": 1,
                            "components": [
                                {"type": 2, "style": 1, "label": "Playing", "custom_id": "rpc_btn_playing", "emoji": {"name": "🎮"}},
                                {"type": 2, "style": 1, "label": "Listening", "custom_id": "rpc_btn_listening", "emoji": {"name": "🎧"}},
                                {"type": 2, "style": 1, "label": "Watching", "custom_id": "rpc_btn_watching", "emoji": {"name": "📺"}}
                            ]
                        },
                        {
                            "type": 1,
                            "components": [
                                {"type": 2, "style": 4, "label": "Clear Status", "custom_id": "rpc_btn_clear", "emoji": {"name": "🛑"}}
                            ]
                        }
                    ]
                }
            ]
        }
        route = discord.http.Route("POST", "/channels/{channel_id}/messages", channel_id=ctx.channel.id)
        await self.bot.http.request(route, json=payload)

    # ==========================================
    # 2. RAW INTERACTION HANDLER
    # ==========================================
    @commands.Cog.listener()
    async def on_socket_response(self, msg):
        if msg.get("t") != "INTERACTION_CREATE":
            return

        data = msg.get("d", {})
        interaction_type = data.get("type")
        custom_id = data.get("data", {}).get("custom_id", "")
        interaction_id = data.get("id")
        interaction_token = data.get("token")

        callback_route = discord.http.Route(
            "POST", 
            "/interactions/{interaction_id}/{interaction_token}/callback",
            interaction_id=interaction_id,
            interaction_token=interaction_token
        )

        # --- BUTTON CLICKS ---
        if interaction_type == 3:
            if custom_id in ["rpc_btn_playing", "rpc_btn_listening", "rpc_btn_watching"]:
                act_type = custom_id.split("_")[-1]
                modal_payload = {
                    "type": 9,
                    "data": {
                        "title": f"Set {act_type.title()} Status",
                        "custom_id": f"rpc_modal_submit_{act_type}",
                        "components": [
                            {"type": 1, "components": [{"type": 4, "custom_id": "rpc_name", "label": "App/Game Name", "style": 1, "placeholder": "e.g. Minecraft", "required": True}]},
                            {"type": 1, "components": [{"type": 4, "custom_id": "rpc_details", "label": "Details (Line 1)", "style": 1, "required": False}]},
                            {"type": 1, "components": [{"type": 4, "custom_id": "rpc_state", "label": "State (Line 2)", "style": 1, "required": False}]},
                            {"type": 1, "components": [{"type": 4, "custom_id": "rpc_image", "label": "Discord CDN Image URL", "style": 1, "placeholder": "https://cdn.discordapp.com/...", "required": False}]}
                        ]
                    }
                }
                await self.bot.http.request(callback_route, json=modal_payload)
                return

            elif custom_id == "rpc_btn_clear":
                self.bot.locked_presence = False
                await self.bot.change_presence(activity=None)
                response = {"type": 4, "data": {"content": "🛑 RPC forcefully cleared.", "flags": 64}}
                await self.bot.http.request(callback_route, json=response)
                return

        # --- MODAL SUBMITS ---
        if interaction_type == 5 and custom_id.startswith("rpc_modal_submit_"):
            act_type_str = custom_id.replace("rpc_modal_submit_", "")
            components = data.get("data", {}).get("components", [])
            name, details, state, image_url = None, None, None, None
            
            for row in components:
                for comp in row.get("components", []):
                    cid = comp.get("custom_id")
                    val = comp.get("value")
                    if cid == "rpc_name": name = val
                    elif cid == "rpc_details": details = val
                    elif cid == "rpc_state": state = val
                    elif cid == "rpc_image": image_url = val

            types = {"playing": discord.ActivityType.playing, "listening": discord.ActivityType.listening, "watching": discord.ActivityType.watching}
            assets = {}
            if image_url:
                assets["large_image"] = format_image_url(image_url)
                if details: assets["large_text"] = details

            try:
                self.bot.locked_presence = True
                await self.bot.change_presence(activity=discord.Activity(
                    type=types[act_type_str], name=name, details=details, state=state,
                    assets=assets if assets else None
                ))
                response = {"type": 4, "data": {"content": f"✅ RPC updated to **{act_type_str.title()} {name}**.", "flags": 64}}
            except Exception as e:
                response = {"type": 4, "data": {"content": f"❌ Failed to set RPC: {e}", "flags": 64}}

            await self.bot.http.request(callback_route, json=response)
            return

    # ==========================================
    # 3. TEXT COMMANDS
    # ==========================================
    @commands.command()
    async def rpc(self, ctx, activity_type: str, *, args):
        """advanced rpc. usage: .rpc playing name | details | state | image | elapsed"""
        activity_type = activity_type.lower()
        parts = [p.strip() for p in args.split("|")]
        name = parts[0] if len(parts) > 0 else "chrm"

        timestamps = None
        if "elapsed" in [p.lower() for p in parts]:
            timestamps = {"start": int(datetime.now().timestamp())}
            parts.pop()

        large_img = parts[3] if len(parts) > 3 and parts[3] else None
        details = parts[1] if len(parts) > 1 and parts[1] else None
        state = parts[2] if len(parts) > 2 and parts[2] else None

        types = {"playing": discord.ActivityType.playing, "watching": discord.ActivityType.watching, "listening": discord.ActivityType.listening, "competing": discord.ActivityType.competing}
        if activity_type not in types:
            return await ctx.send(f"{self.bot.config.get_emoji('error')} invalid type.")

        assets = {}
        if large_img:
            assets["large_image"] = format_image_url(large_img)
            if details: assets["large_text"] = details

        try:
            self.bot.locked_presence = True
            await self.bot.change_presence(activity=discord.Activity(
                type=types[activity_type], name=name, details=details, state=state,
                assets=assets if assets else None, timestamps=timestamps
            ))
            await ctx.send(f"{self.bot.config.get_emoji('success')} rpc updated: {activity_type} **{name}**")
        except Exception as e:
            await ctx.send(f"{self.bot.config.get_emoji('error')} error: {e}")

    @commands.command()
    async def stream(self, ctx, url: str, *, title):
        if not url.startswith("http"):
            return await ctx.send(f"{self.bot.config.get_emoji('error')} invalid url.")
        self.bot.locked_presence = True
        await self.bot.change_presence(activity=discord.Streaming(name=title, url=url))
        await ctx.send(f"{self.bot.config.get_emoji('success')} now streaming: **{title}**")

    @commands.command()
    async def customstatus(self, ctx, *, text):
        self.bot.locked_presence = True
        await self.bot.change_presence(activity=discord.CustomActivity(name=text))
        await ctx.send(f"{self.bot.config.get_emoji('success')} custom status set to: {text}")

    @commands.command()
    async def clearstatus(self, ctx):
        self.bot.locked_presence = False
        await self.bot.change_presence(activity=None)
        await ctx.send(f"{self.bot.config.get_emoji('success')} presence completely wiped.")

    # ==========================================
    # 4. STATUS ROTATOR
    # ==========================================
    @commands.command()
    async def startrotator(self, ctx, *, args):
        match = re.search(r'\|\s*(\d+)([smh])$', args)
        if not match: return await ctx.send("missing time. usage: `.startrotator status1, status2 | 5m`")
        amount, unit = int(match.group(1)), match.group(2)
        total_seconds = amount * {'s': 1, 'm': 60, 'h': 3600}[unit]
        statuses = [s.strip() for s in args[:match.start()].strip().split(",") if s.strip()]
        if not statuses: return await ctx.send("no statuses provided.")
        if self.custom_rotator_task and not self.custom_rotator_task.done(): self.custom_rotator_task.cancel()
        
        self.bot.locked_presence = True
        self.custom_rotator_task = asyncio.create_task(self._run_custom_rotator(statuses, total_seconds))
        await ctx.send(f"{self.bot.config.get_emoji('success')} rotator started.")

    async def _run_custom_rotator(self, statuses, interval):
        try:
            index = 0
            while True:
                await self.bot.change_presence(activity=discord.CustomActivity(name=statuses[index % len(statuses)]))
                index += 1
                await asyncio.sleep(interval)
        except asyncio.CancelledError: pass

    @commands.command()
    async def stoprotator(self, ctx):
        if self.custom_rotator_task and not self.custom_rotator_task.done():
            self.custom_rotator_task.cancel()
            self.bot.locked_presence = False
            await self.bot.change_presence(activity=None)
            await ctx.send(f"{self.bot.config.get_emoji('success')} rotator stopped.")

async def setup(bot):
    await bot.add_cog(RPC(bot))
