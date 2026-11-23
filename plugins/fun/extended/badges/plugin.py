import discord
from discord.ext import commands
from discord.http import Route
import asyncio
import itertools
import random
import time
import uuid

class AutoBadgesMixin:
    """Commands for this sub-cog; assembled into the package cog."""
    @commands.command()
    async def testrpc(self, ctx):
        """tests if the bot can change your presence at all"""
        await ctx.send("testing rpc...")
        print("[debug] testing rpc")
        try:
            await self.bot.change_presence(activity=discord.Game(name="chrm test"))
            print("[debug] rpc test successful")
            await ctx.send("rpc test successful. check your profile.")
        except Exception as e:
            print(f"[debug] rpc test failed: {e}")
            await ctx.send(f"rpc test failed: {e}")

    @commands.command()
    async def autobadges(self, ctx, amount: int = 100, game_time: int = 5):
        """spoofs playing games. usage: .autobadges <amount> <seconds_per_game>"""
        if self.is_running:
            error = self.bot.config.get_emoji("error")
            return await ctx.send(f"{error} autobadges is already running. use `.stopbadges` to cancel.")

        loading = self.bot.config.get_emoji("loading")
        msg = await ctx.send(f"{loading} downloading game database...")

        try:
            catalogue = await self.get_games()
        except Exception as e:
            error = self.bot.config.get_emoji("error")
            return await msg.edit(content=f"{error} game database download failed: `{e}`")

        if not catalogue:
            error = self.bot.config.get_emoji("error")
            return await msg.edit(content=f"{error} game database is empty.")

        random.shuffle(catalogue)
        target_games = catalogue[:max(1, amount)]

        total_seconds = len(target_games) * game_time
        total_minutes = total_seconds // 60

        success = self.bot.config.get_emoji("success")
        await msg.edit(content=f"{success} starting rotation for **{len(target_games)}** games (~{total_minutes}m total).")

        self.is_running = True
        self.badge_task = self.bot.loop.create_task(self.rotate_badges(target_games, game_time, msg))

    async def rotate_badges(self, games, game_time, status_msg):
        try:
            count = 0
            for game in games:
                game_name, game_id = game.name, game.app_id
                if not self.is_running:
                    break

                # Send BOTH name and application_id
                activity = discord.Activity(
                    type=discord.ActivityType.playing,
                    name=game_name,
                    application_id=game_id
                )
                
                try:
                    await self.bot.change_presence(activity=activity)
                    print(f"[autobadges] set presence to {game_name} ({game_id})")
                except Exception as e:
                    print(f"failed to set presence for {game_name}: {e}")
                    await asyncio.sleep(10)

                await asyncio.sleep(game_time)
                
                count += 1
                if count % 10 == 0:
                    await status_msg.edit(content=f"playing game {count}/{len(games)} (current: {game_name})...")

            self.is_running = False
            if self.bot.is_ready():
                await self.bot.change_presence(activity=discord.CustomActivity(name="chrm on top"))
                success = self.bot.config.get_emoji("success")
                await status_msg.edit(content=f"{success} finished rotating {count} games.")
                
        except asyncio.CancelledError:
            self.is_running = False
        except Exception as e:
            print(f"[autobadges] error: {e}")
            self.is_running = False

    @commands.command()
    async def stopbadges(self, ctx):
        if self.badge_task and not self.badge_task.done():
            self.is_running = False
            self.badge_task.cancel()
            emoji = self.bot.config.get_emoji("success")
            await ctx.send(f"{emoji} autobadges rotation stopped.")
        else:
            error = self.bot.config.get_emoji("error")
            await ctx.send(f"{error} autobadges is not running.")

    # ------------------------------------------------------------------
    # Game Time / Game Variety telemetry
    #
    # Presence is not what those badges count. The desktop client reports
    # launch_game + running_game_heartbeat to /science with a duration the
    # backend trusts, and the badge job aggregates that nightly. So the only
    # way to move them from here is to send the same events.
    # ------------------------------------------------------------------

    async def analytics_token(self):
        """fetch the per-session analytics token /science wants, cached 12h"""
        now = time.time()
        cached = self._analytics.get("token")
        if cached and now - self._analytics.get("at", 0) < 12 * 3600:
            return cached

        data = await self.bot.http.request(
            Route("GET", "/users/@me"), params={"with_analytics_token": "true"}
        )
        token = data.get("analytics_token")
        if not token:
            raise RuntimeError("discord did not return an analytics token")

        self._analytics = {"token": token, "at": now}
        return token

    def telemetry_events(self, name, app_id, hours, session_id, sequence):
        """one full fake play session: initial heartbeat, launch, final heartbeat"""
        duration = int(hours * 3600 * 1000)
        now = int(time.time() * 1000)
        origin = max(now - duration, 1)

        def heartbeat(timestamp, tracked, initial, final):
            return {
                "type": "running_game_heartbeat",
                "properties": {
                    "client_track_timestamp": timestamp,
                    "client_heartbeat_session_id": self._hb_session,
                    "event_sequence_number": next(sequence),
                    "game_id": app_id,
                    "game_name": name,
                    "game_metadata": None,
                    "game_executable": "game.exe",
                    "game_detection_enabled": True,
                    "initial_heartbeat": initial,
                    "final_heartbeat": final,
                    "game_session_id": session_id,
                    "duration_tracked_ms": tracked,
                    "rtc_connection_id": None,
                    "media_session_id": None,
                    "launch_signature": self._launch_sig,
                    "client_app_state": "focused",
                    "client_send_timestamp": timestamp,
                },
            }

        def launch_event():
            return {
                "type": "launch_game",
                "properties": {
                    "client_track_timestamp": now,
                    "client_heartbeat_session_id": self._hb_session,
                    "event_sequence_number": next(sequence),
                    "game": name,
                    "game_id": app_id,
                    "verified": True,
                    "elevated": False,
                    "is_launcher": False,
                    "game_platform": "desktop",
                    "detection_method": "verified_game",
                    "is_overlay_enabled": False,
                    "is_overlay_game_enabled": True,
                    "is_overlay_game_source": "OOP_DEFAULT_DATABASE",
                    "fullscreen_type": "UNKNOWN",
                    "hardware_display_count": 1,
                    "overlay_method": "Disabled",
                    "activity_status_enabled": True,
                    "activity_status_shared_guilds": [],
                    "current_user_status": "online",
                    "game_detection_enabled": True,
                    "executable_path": "game.exe",
                    "voice_channel_id": None,
                    "voice_channel_type": None,
                    "voice_channel_bitrate": None,
                    "voice_channel_guild_id": None,
                    "hidden_by_distributor": False,
                    "game_metadata": None,
                    "client_performance_cpu": None,
                    "client_performance_memory": None,
                    "cpu_core_count": None,
                    "accessibility_features": 0,
                    "rendered_locale": "en-US",
                    "launch_signature": self._launch_sig,
                    "client_rtc_state": None,
                    "client_app_state": "focused",
                    "client_send_timestamp": now,
                },
            }

        # Built left to right so event_sequence_number follows the payload order.
        return [heartbeat(origin, 0, True, False), launch_event(), heartbeat(now, duration, False, True)]

    @commands.command()
    async def farmtime(self, ctx, games: int = 100, hours_each: float = 50):
        """credits Game Time / Game Variety by reporting fake desktop play sessions.

        usage: .farmtime [games] [hours_each]  -- 100 x 50 = 5000h + 100 titles.
        presence can never move these badges; only /science telemetry does. Discord
        aggregates it every 24-48h, and it needs "Use data to personalize my Discord
        experience" enabled in User Settings > Data & Privacy.
        """
        error = self.bot.config.get_emoji("error")
        success = self.bot.config.get_emoji("success")
        loading = self.bot.config.get_emoji("loading")

        games = max(1, min(int(games), 100))
        hours_each = max(0.5, min(float(hours_each), 5000.0))

        msg = await ctx.send(f"{loading} requesting analytics token...")
        try:
            token = await self.analytics_token()
        except Exception as e:
            return await msg.edit(content=f"{error} could not get an analytics token: `{e}`")

        try:
            catalogue = await self.get_games()
        except Exception as e:
            return await msg.edit(content=f"{error} failed to download game database: `{e}`")
        if not catalogue:
            return await msg.edit(content=f"{error} game database is empty.")

        random.shuffle(catalogue)
        picks = catalogue[:games]

        # One session identity for the whole run, like a client that stayed open.
        self._hb_session = str(uuid.uuid4())
        self._launch_sig = str(uuid.uuid4())
        sequence = itertools.count(1)

        sent, failed = 0, 0
        for offset in range(0, len(picks), 10):
            chunk = picks[offset:offset + 10]
            events = []
            for game in chunk:
                events.extend(
                    self.telemetry_events(game.name, game.app_id, hours_each, str(uuid.uuid4()), sequence)
                )
            try:
                await self.bot.http.request(Route("POST", "/science"), json={"token": token, "events": events})
                sent += len(chunk)
            except Exception as e:
                failed += len(chunk)
                print(f"[farmtime] batch failed: {e}")

            await msg.edit(content=f"{loading} reported {sent}/{len(picks)} games ({sent * hours_each:,.0f}h)...")
            await asyncio.sleep(1)

        credited = sent * hours_each
        lines = [
            f"{success} reported **{sent}** games x **{hours_each:g}h** = **{credited:,.0f}h** of game time.",
            "badges update on Discord's 24-48h aggregation, not instantly.",
            "needs `Use data to personalize my Discord experience` on in Data & Privacy.",
            "this is spoofed telemetry - it violates Discord's ToS, treat the account as at risk.",
        ]
        if failed:
            lines.insert(1, f"{error} {failed} games failed to send (rate limit or auth).")
        await msg.edit(content="\n".join(lines))
