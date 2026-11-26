"""Group activities: one lobby, a reaction to join, then a game everyone plays.

``.lobby wordle 10`` posts a card, adds ✅, waits ten seconds (or until ``.start``),
reads the reactions and turns the roster into a multiplayer wordle. ``.lobby
trivia`` and ``.lobby hangman`` reuse the single-player games already in this cog
-- there the lobby is only the "who is in" part, and the game is the existing one.

Why reactions and not buttons: a self-bot cannot send Components V2 or real
buttons (see ``core/ui/cv2.py``), so a ✅ is the one join control that works for
everyone in the channel, including people who never run a command. ``.join``
exists for anyone who would rather type it.

State is per channel in ``party_games`` and deliberately not persisted: a lobby
that survives a restart is a message nobody can join any more.
"""
from __future__ import annotations

import asyncio
import random
import time

from discord.ext import commands

from core import prefs
from plugins.fun.extended.wordle.plugin import MAX_GUESSES, WORD_LENGTH, board_line, score
from plugins.fun.extended.wordle.words import ANSWERS

#: how long a lobby stays open unless told otherwise
DEFAULT_SECONDS = 10
MIN_SECONDS, MAX_SECONDS = 5, 120
#: the join control
JOIN_EMOJI = "✅"
#: guesses each player gets in a party wordle
PARTY_TRIES = 4
#: games a lobby can start
GAMES = ("wordle", "trivia", "hangman")
#: names shown in the lobby card before it gets silly
MAX_ROSTER = 20


def _mention(user_id) -> str:
    return f"<@{user_id}>"


class PartyMixin:
    """Commands for this sub-cog; assembled into the package cog."""

    # ------------------------------------------------------------ helpers
    def _party_game(self, ctx):
        return self.party_games.get(getattr(ctx.channel, "id", 0))

    def _party_channel(self, ctx):
        return getattr(ctx, "channel", None)

    def _party_names(self, state) -> str:
        names = [player["name"] for player in state["players"].values()]
        shown = ", ".join(names[:MAX_ROSTER])
        if len(names) > MAX_ROSTER:
            shown += f" +{len(names) - MAX_ROSTER}"
        return shown or "nobody yet"

    def _lobby_text(self, state) -> str:
        left = max(0, int(state["ends"] - time.time()))
        lines = [
            f"### {state['game']} lobby",
            f"react {JOIN_EMOJI} to join · `.join` works too · starts <t:{int(state['ends'])}:R> ({left}s)",
            f"**{len(state['players'])}** in · {self._party_names(state)}",
        ]
        if state.get("invites"):
            lines.append("invited " + " ".join(_mention(uid) for uid in state["invites"]))
        lines.append(f"-# `.start` begins now · `.endparty` cancels · host <@{state['host']}>")
        return "\n".join(lines)

    async def _edit_lobby(self, state):
        message = state.get("message")
        if message is None:
            return
        try:
            await message.edit(content=self._lobby_text(state))
        except Exception as exc:  # noqa: BLE001 - edited away, no perms, stale
            print(f"[PARTY] lobby update failed: {type(exc).__name__}: {exc}")

    def _party_add(self, state, user) -> bool:
        """Add ``user`` to the roster; False when they are already in it."""
        user_id = getattr(user, "id", None)
        if not user_id:
            return False
        # a real bot in the channel is not a player; the account running this is
        # (it is the host, and its own ✅ is how it joins without typing)
        if getattr(user, "bot", False):
            return False
        if user_id in state["players"]:
            return False
        name = getattr(user, "display_name", None) or getattr(user, "name", str(user_id))
        state["players"][user_id] = {
            "name": str(name)[:24],
            "tries": 0,
            "rows": [],
            "solved": False,
            "out": False,
        }
        return True

    async def _collect_reactions(self, state):
        """Fold every ✅ reaction on the lobby card into the roster."""
        message = state.get("message")
        for reaction in list(getattr(message, "reactions", None) or []):
            if str(getattr(reaction, "emoji", "")) != JOIN_EMOJI:
                continue
            try:
                async for user in reaction.users():
                    self._party_add(state, user)
            except Exception as exc:  # noqa: BLE001 - reaction cleared, no intent
                print(f"[PARTY] could not read reactions: {type(exc).__name__}: {exc}")

    # ------------------------------------------------------------ lobby
    @commands.command(name="lobby", aliases=["gamelobby", "partyup"])
    async def lobby(self, ctx, game: str = "wordle", *args):
        """open a lobby: react to join, then the game starts. usage: .lobby wordle 10 @friend"""
        kind = (game or "").strip().lower()
        if kind not in GAMES:
            return await ctx.warn("games: " + ", ".join(f"`{name}`" for name in GAMES))

        seconds = DEFAULT_SECONDS
        invites = []
        for raw in args:
            token = str(raw)
            if token.isdigit():
                seconds = max(MIN_SECONDS, min(MAX_SECONDS, int(token)))
            elif token.startswith("<@"):
                digits = "".join(char for char in token if char.isdigit())
                if digits.isdigit():
                    invites.append(int(digits))
        for user in getattr(ctx.message, "mentions", None) or []:
            user_id = getattr(user, "id", None)
            if user_id and user_id not in invites:
                invites.append(user_id)

        existing = self._party_game(ctx)
        if existing is not None:
            if existing.get("kind") == "lobby":
                return await ctx.warn(
                    "a lobby is already open here — `.join` it, `.start` it or `.endparty` it."
                )
            return await ctx.warn("a party game is already running here — `.party` to see it.")

        channel_id = getattr(ctx.channel, "id", 0)
        state = {
            "kind": "lobby",
            "game": kind,
            "host": getattr(getattr(ctx, "author", None), "id", 0),
            "players": {},
            "invites": invites,
            "started": time.time(),
            "ends": time.time() + seconds,
            "event": asyncio.Event(),
            "message": None,
        }
        self._party_add(state, getattr(ctx, "author", None))
        self.party_games[channel_id] = state

        state["message"] = await ctx.send(self._lobby_text(state))
        try:
            await state["message"].add_reaction(JOIN_EMOJI)
        except Exception as exc:  # noqa: BLE001 - missing add-reactions permission
            print(f"[PARTY] could not add the join reaction: {type(exc).__name__}: {exc}")

        try:
            await asyncio.wait_for(state["event"].wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass
        except asyncio.CancelledError:
            raise

        await self._collect_reactions(state)
        await self._begin(ctx, state)

    @commands.command(name="join", aliases=["joinparty"])
    async def join(self, ctx):
        """join the open lobby. usage: .join"""
        state = self._party_game(ctx)
        if state is None or state.get("kind") != "lobby":
            return await ctx.warn("no lobby open here. `.lobby wordle` starts one.")
        if not self._party_add(state, getattr(ctx, "author", None)):
            return await ctx.warn("you are already in this lobby.")
        await self._edit_lobby(state)
        await ctx.approve(f"you are in — **{len(state['players'])}** playing {state['game']}.")

    @commands.command(name="start", aliases=["startparty"])
    async def start(self, ctx):
        """start the lobby now instead of waiting. usage: .start"""
        state = self._party_game(ctx)
        if state is None or state.get("kind") != "lobby":
            return await ctx.warn("no lobby open here. `.lobby wordle` starts one.")
        state["event"].set()
        await ctx.approve("starting now.")

    @commands.command(name="endparty", aliases=["endgame"])
    async def endparty(self, ctx):
        """cancel the lobby or the party game here. usage: .endparty"""
        state = self._party_game(ctx)
        if state is None:
            return await ctx.warn("nothing is running here.")
        self.party_games.pop(getattr(ctx.channel, "id", 0), None)
        state["cancelled"] = True
        if state.get("kind") == "lobby":
            state["event"].set()
        if state.get("kind") == "wordle" and state.get("answer"):
            return await ctx.approve(f"ended — the word was **{state['answer']}**.")
        await ctx.approve("party ended.")

    # ------------------------------------------------------------ wordle
    def _party_board(self, state) -> str:
        colorblind = bool(prefs.get(self.bot, "wordle_colorblind", False))
        lines = [f"### party wordle · {len(state['players'])} players"]
        for player in state["players"].values():
            if player["solved"]:
                status = "solved ✅"
            elif player["out"]:
                status = "out ❌"
            else:
                status = f"{PARTY_TRIES - player['tries']} left"
            lines.append(f"**{player['name']}** · {status}")
            lines.extend(f"  {row}" for row in player["rows"][-MAX_GUESSES:])
        lines.append("-# `.gw <word>` to guess · `.party` for this board")
        return "\n".join(lines)

    async def _start_party_wordle(self, ctx, state):
        state["kind"] = "wordle"
        state["answer"] = random.choice(ANSWERS)
        state["started"] = time.time()
        state.pop("event", None)
        await ctx.send(
            f"### party wordle · {len(state['players'])} players\n"
            f"five letters, **{PARTY_TRIES}** guesses each, first correct answer wins.\n"
            f"{self._party_names(state)} — `.gw <word>` when you are ready."
        )

    @commands.command(name="gw", aliases=["groupguess", "partyguess"])
    async def gw(self, ctx, *, word: str = ""):
        """guess in a party wordle. usage: .gw crane"""
        state = self._party_game(ctx)
        if state is None or state.get("kind") != "wordle":
            return await ctx.warn("no party wordle here. `.lobby wordle` starts one.")

        player = state["players"].get(getattr(getattr(ctx, "author", None), "id", 0))
        if player is None:
            return await ctx.warn("you are not in this game — join the next lobby.")
        if player["solved"] or player["out"]:
            return await ctx.warn("you are done for this round — watch the rest play out.")

        guess = "".join((word or "").lower().split())
        if len(guess) != WORD_LENGTH or not guess.isalpha() or not guess.isascii():
            return await ctx.warn(f"five letters, nothing else. `{word}` is not a guess.")

        colorblind = bool(prefs.get(self.bot, "wordle_colorblind", False))
        player["tries"] += 1
        player["rows"].append(board_line(state["answer"], guess, colorblind))
        answer = state["answer"]

        if guess == answer:
            player["solved"] = True
            self.party_games.pop(getattr(ctx.channel, "id", 0), None)
            return await ctx.send(
                f"### 🏆 {player['name']}\n"
                f"the word was **{answer}** — solved in **{player['tries']}** guess"
                f"{'' if player['tries'] == 1 else 'es'}.\n"
                f"{self._party_board(state)}"
            )

        if player["tries"] >= PARTY_TRIES:
            player["out"] = True
            await ctx.send(f"**{player['name']}** is out of guesses.")

        alive = [item for item in state["players"].values() if not item["solved"] and not item["out"]]
        if not alive:
            self.party_games.pop(getattr(ctx.channel, "id", 0), None)
            return await ctx.send(
                f"### party wordle · nobody got it\nthe word was **{answer}**.\n"
                f"{self._party_board(state)}"
            )

        await ctx.send(self._party_board(state))

    # ------------------------------------------------------------ status
    @commands.command(name="party", aliases=["partygame"])
    async def party(self, ctx):
        """who is in, and what the party is doing. usage: .party"""
        state = self._party_game(ctx)
        if state is None:
            return await ctx.warn("nothing is running here. `.lobby wordle` starts one.")
        if state.get("kind") == "lobby":
            return await ctx.send(self._lobby_text(state))
        if state.get("kind") == "wordle":
            return await ctx.send(self._party_board(state))
        return await ctx.warn(f"a **{state.get('kind')}** game is running here.")

    # ------------------------------------------------------------ single-player games
    async def _start_single(self, ctx, state, kind: str):
        """Hand a lobby over to one of the existing per-channel games."""
        roster = self._party_names(state)
        players = len(state["players"])
        self.party_games.pop(getattr(ctx.channel, "id", 0), None)
        await ctx.send(f"### 🎮 {kind} · {players} playing\n{roster}")

        command = getattr(type(self), kind, None)
        callback = getattr(command, "callback", command)
        if callback is None:
            return await ctx.deny(f"`{kind}` is not loaded in this build.")
        try:
            await callback(self, ctx)
        except Exception as exc:  # noqa: BLE001 - never traceback into the channel
            print(f"[PARTY] {kind} failed to start: {type(exc).__name__}: {exc}")
            await ctx.deny(f"`{kind}` did not start: {exc}")

    async def _begin(self, ctx, state):
        if state.get("cancelled"):
            return None
        if not state["players"]:
            self.party_games.pop(getattr(ctx.channel, "id", 0), None)
            return await ctx.warn(
                "nobody joined — `.lobby` again, and mention whoever you want in it."
            )
        if state["game"] == "wordle":
            return await self._start_party_wordle(ctx, state)
        return await self._start_single(ctx, state, state["game"])
