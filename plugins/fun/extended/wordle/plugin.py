"""Wordle: one five-letter word, six guesses, one channel at a time.

The board is plain text (a self-bot cannot send embeds), the answer pool is
:mod:`plugins.fun.extended.wordle.words`, and guesses are accepted from any
five-letter word so nobody has to fight a dictionary.

Preferences are read from :mod:`core.prefs`: ``wordle_hard`` rejects guesses that
ignore revealed letters, ``wordle_colorblind`` swaps green/yellow for blue/orange,
and ``wordle_spoiler`` wraps the board in spoiler tags. Stats live in
``settings.features.wordle`` and persist through the same PATCH as every other
feature.
"""
from __future__ import annotations

import random
import string
import time

from discord.ext import commands

from core import api, prefs
from plugins.fun.extended.wordle.words import ANSWERS

MAX_GUESSES = 6
WORD_LENGTH = 5

SQUARES = {
    "normal": {"green": "🟩", "yellow": "🟨", "grey": "⬛"},
    "colorblind": {"green": "🟦", "yellow": "🟧", "grey": "⬛"},
}


def normalise_stats(raw) -> dict:
    """A stats dict with every key present, whatever the dashboard sent."""
    base = {
        "played": 0,
        "wins": 0,
        "streak": 0,
        "best": 0,
        "distribution": {str(row): 0 for row in range(1, MAX_GUESSES + 1)},
    }
    if not isinstance(raw, dict):
        return base
    for key in ("played", "wins", "streak", "best"):
        try:
            base[key] = max(0, int(raw.get(key, 0)))
        except (TypeError, ValueError):
            pass
    distribution = raw.get("distribution")
    if isinstance(distribution, dict):
        for row in base["distribution"]:
            try:
                base["distribution"][row] = max(0, int(distribution.get(row, 0)))
            except (TypeError, ValueError):
                pass
    return base


def score(answer: str, guess: str) -> list:
    """Wordle marks for ``guess`` against ``answer``, duplicate letters included."""
    marks = ["grey"] * WORD_LENGTH
    left = list(answer)
    for index, (wanted, given) in enumerate(zip(answer, guess)):
        if given == wanted:
            marks[index] = "green"
            left[index] = None
    for index, given in enumerate(guess):
        if marks[index] == "green":
            continue
        if given in left:
            marks[index] = "yellow"
            left[left.index(given)] = None
    return marks


def board_line(answer: str, guess: str, colorblind: bool) -> str:
    squares = SQUARES["colorblind" if colorblind else "normal"]
    return "".join(squares[mark] for mark in score(answer, guess)) + f" `{guess}`"


def hard_miss(guesses, guess: str, answer: str):
    """The revealed letter ``guess`` ignored, or ``None`` in hard mode."""
    for previous in guesses:
        marks = score(answer, previous)
        for index, mark in enumerate(marks):
            if mark == "green" and guess[index] != previous[index]:
                return previous[index]
            if mark == "yellow" and previous[index] not in guess:
                return previous[index]
    return None


class WordleMixin:
    """Commands for this sub-cog; assembled into the package cog."""

    # ------------------------------------------------------------ helpers
    def _wordle_game(self, ctx):
        return self.wordle_games.get(getattr(ctx.channel, "id", 0))

    def _wordle_stats(self) -> dict:
        self.wordle_stats = normalise_stats(self.wordle_stats)
        return self.wordle_stats

    async def _save_wordle_stats(self):
        await api.save_feature(self.bot, "wordle", self._wordle_stats(), tag="WORDLE")

    def _wordle_options(self) -> dict:
        return {
            "colorblind": bool(prefs.get(self.bot, "wordle_colorblind", False)),
            "spoiler": bool(prefs.get(self.bot, "wordle_spoiler", False)),
        }

    def _wordle_board(self, game) -> str:
        options = self._wordle_options()
        lines = [f"### wordle · {len(game['guesses'])}/{MAX_GUESSES}"]
        lines.extend(
            board_line(game["answer"], guess, options["colorblind"])
            for guess in game["guesses"]
        )
        if game["hard"]:
            lines.append("-# hard mode")
        board = "\n".join(lines)
        return f"||{board}||" if options["spoiler"] else board

    # ------------------------------------------------------------ commands
    @commands.command(name="wordle", aliases=["wd"])
    async def wordle(self, ctx):
        """start a wordle. usage: .wordle"""
        game = self._wordle_game(ctx)
        if game and not game["done"]:
            return await ctx.send(
                f"{self.bot.config.get_emoji('error')} a wordle is already running here. "
                "`.guess <word>` it or `.wordleend` to reveal it.\n\n"
                + self._wordle_board(game)
            )

        self.wordle_games[getattr(ctx.channel, "id", 0)] = {
            "answer": random.choice(ANSWERS),
            "guesses": [],
            "hard": bool(prefs.get(self.bot, "wordle_hard", False)),
            "started": time.time(),
            "done": False,
        }
        await ctx.send(
            "### wordle\n"
            "six guesses, five letters each. `.guess <word>` to play, "
            "`.wordleend` to give up.\n"
            "🟩 right spot · 🟨 wrong spot · ⬛ not in the word"
        )

    @commands.command(name="guess", aliases=["wg", "wguess"])
    async def guess(self, ctx, *, word: str = ""):
        """guess the wordle. usage: .guess crane"""
        game = self._wordle_game(ctx)
        if not game or game["done"]:
            return await ctx.warn("no wordle here. start one with `.wordle`.")

        guess = "".join(word.lower().split())
        if len(guess) != WORD_LENGTH or not guess.isalpha() or not guess.isascii():
            return await ctx.warn(f"five letters, nothing else. `{word}` is not a guess.")

        if game["hard"]:
            missed = hard_miss(game["guesses"], guess, game["answer"])
            if missed:
                return await ctx.warn(
                    f"hard mode: your guess has to use the revealed **{missed.upper()}**."
                )

        game["guesses"].append(guess)
        marks = score(game["answer"], guess)
        row = board_line(game["answer"], guess, self._wordle_options()["colorblind"])

        if guess == game["answer"]:
            game["done"] = True
            stats = self._wordle_stats()
            stats["played"] += 1
            stats["wins"] += 1
            stats["streak"] += 1
            stats["best"] = max(stats["best"], stats["streak"])
            stats["distribution"][str(len(game["guesses"]))] += 1
            await self._save_wordle_stats()
            return await ctx.send(
                f"### wordle · {len(game['guesses'])}/{MAX_GUESSES} ✅\n"
                f"{row}\n\nthe word was **{game['answer']}** — "
                f"streak **{stats['streak']}**, best **{stats['best']}**."
            )

        if len(game["guesses"]) >= MAX_GUESSES:
            game["done"] = True
            stats = self._wordle_stats()
            stats["played"] += 1
            stats["streak"] = 0
            await self._save_wordle_stats()
            return await ctx.send(
                f"### wordle · {MAX_GUESSES}/{MAX_GUESSES} ❌\n"
                f"{row}\n\nout of guesses — it was **{game['answer']}**."
            )

        await ctx.send(self._wordle_board(game))

    @commands.command(name="wordleend", aliases=["wend", "giveup"])
    async def wordleend(self, ctx):
        """reveal the running wordle and end it. usage: .wordleend"""
        game = self._wordle_game(ctx)
        if not game or game["done"]:
            return await ctx.warn("no wordle here. start one with `.wordle`.")

        game["done"] = True
        stats = self._wordle_stats()
        stats["played"] += 1
        stats["streak"] = 0
        await self._save_wordle_stats()
        await ctx.send(
            f"the word was **{game['answer']}** — {len(game['guesses'])} guess"
            f"{'' if len(game['guesses']) == 1 else 'es'} in. streak reset."
        )

    @commands.command(name="wordlestats", aliases=["wstats"])
    async def wordlestats(self, ctx):
        """your wordle record. usage: .wordlestats"""
        stats = self._wordle_stats()
        played, wins = stats["played"], stats["wins"]
        rate = f"{wins / played * 100:.0f}%" if played else "—"
        lines = [
            "### wordle stats",
            f"played **{played}** · won **{wins}** · win rate **{rate}**",
            f"streak **{stats['streak']}** · best **{stats['best']}**",
        ]
        top = max(stats["distribution"].values(), default=0)
        for row in range(1, MAX_GUESSES + 1):
            count = stats["distribution"][str(row)]
            bar = "█" * (round(count / top * 10) if top else 0)
            lines.append(f"`{row}` {bar or '·'} {count}")
        lines.append("`.wordle` to play again")
        await ctx.send("\n".join(lines))
