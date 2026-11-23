"""Hangman: six wrong letters, one word per channel."""
from __future__ import annotations

import random

from discord.ext import commands

from plugins.fun.extended.hangman.words import CATEGORIES, WORDS

MAX_WRONG = 6

GALLOWS = [
    "```\n  +---+\n  |   |\n      |\n      |\n      |\n      |\n=========```",
    "```\n  +---+\n  |   |\n  O   |\n      |\n      |\n      |\n=========```",
    "```\n  +---+\n  |   |\n  O   |\n  |   |\n      |\n      |\n=========```",
    "```\n  +---+\n  |   |\n  O   |\n /|   |\n      |\n      |\n=========```",
    "```\n  +---+\n  |   |\n  O   |\n /|\\  |\n      |\n      |\n=========```",
    "```\n  +---+\n  |   |\n  O   |\n /|\\  |\n /    |\n      |\n=========```",
    "```\n  +---+\n  |   |\n  O   |\n /|\\  |\n / \\  |\n      |\n=========```",
]


def mask(word: str, guessed) -> str:
    return " ".join(letter.upper() if letter in guessed or not letter.isalpha() else "_" for letter in word)


class HangmanMixin:
    """Commands for this sub-cog; assembled into the package cog."""

    def _hangman_game(self, ctx):
        return self.hangman_games.get(getattr(ctx.channel, "id", 0))

    def _hangman_board(self, game) -> str:
        wrong = sorted(game["got_wrong"])
        return (
            f"{GALLOWS[min(game['wrong'], MAX_WRONG)]}\n"
            f"`{mask(game['word'], game['guessed'])}`\n"
            f"**{game['category']}** · wrong {game['wrong']}/{MAX_WRONG}"
            + (f": {', '.join(wrong)}" if wrong else "")
        )

    @commands.command(name="hangman")
    async def hangman(self, ctx, category: str = ""):
        """start hangman, optionally by category. usage: .hangman [category]"""
        category = category.strip().lower()
        if category and category not in CATEGORIES:
            return await ctx.warn("categories: " + ", ".join(f"`{name}`" for name in CATEGORIES))

        pool = CATEGORIES if not category else (category,)
        topic = random.choice(pool)
        word = random.choice(WORDS[topic])
        self.hangman_games[getattr(ctx.channel, "id", 0)] = {
            "word": word,
            "category": topic,
            "guessed": set(),
            "got_wrong": set(),
            "wrong": 0,
        }
        game = self._hangman_game(ctx)
        await ctx.send(f"### hangman\n{self._hangman_board(game)}\n`.hguess <letter|word>`")

    @commands.command(name="hguess", aliases=["hangguess"])
    async def hguess(self, ctx, *, guess: str = ""):
        """guess a letter or the whole word. usage: .hguess e"""
        game = self._hangman_game(ctx)
        if not game:
            return await ctx.warn("no hangman here. `.hangman` to start one.")

        guess = guess.strip().lower()
        if not guess:
            return await ctx.warn("usage: `.hguess <letter|word>`")

        if len(guess) > 1:
            if guess == game["word"]:
                self.hangman_games.pop(getattr(ctx.channel, "id", 0), None)
                return await ctx.approve(f"**{game['word'].upper()}** — solved.")
            game["wrong"] += 1
            game["got_wrong"].add(guess)
            if game["wrong"] >= MAX_WRONG:
                self.hangman_games.pop(getattr(ctx.channel, "id", 0), None)
                return await ctx.send(f"{self._hangman_board(game)}\nout of tries — it was **{game['word'].upper()}**.")
            return await ctx.send(f"{self._hangman_board(game)}\nnot the word.")

        letter = guess[0]
        if not letter.isalpha():
            return await ctx.warn("letters only.")
        if letter in game["guessed"] or letter in game["got_wrong"]:
            return await ctx.warn(f"**{letter.upper()}** was already guessed.")

        if letter in game["word"]:
            game["guessed"].add(letter)
            if all(char in game["guessed"] or not char.isalpha() for char in game["word"]):
                self.hangman_games.pop(getattr(ctx.channel, "id", 0), None)
                return await ctx.approve(f"**{game['word'].upper()}** — solved.")
            return await ctx.send(self._hangman_board(game))

        game["got_wrong"].add(letter)
        game["wrong"] += 1
        if game["wrong"] >= MAX_WRONG:
            self.hangman_games.pop(getattr(ctx.channel, "id", 0), None)
            return await ctx.send(f"{self._hangman_board(game)}\nout of tries — it was **{game['word'].upper()}**.")
        await ctx.send(self._hangman_board(game))

    @commands.command(name="hangmanend", aliases=["hend"])
    async def hangmanend(self, ctx):
        """give up on the hangman. usage: .hangmanend"""
        game = self._hangman_game(ctx)
        if not game:
            return await ctx.warn("no hangman here. `.hangman` to start one.")
        self.hangman_games.pop(getattr(ctx.channel, "id", 0), None)
        await ctx.send(f"it was **{game['word'].upper()}**.")
