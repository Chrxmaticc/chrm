"""Trivia: one question per channel, three tries, `.answer` to solve it."""
from __future__ import annotations

import random
import re
import time

from discord.ext import commands

from plugins.fun.extended.trivia.bank import CATEGORIES, QUESTIONS

MAX_TRIES = 3


def normalise(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    for article in ("the ", "a ", "an "):
        if text.startswith(article):
            text = text[len(article):]
    return text


class TriviaMixin:
    """Commands for this sub-cog; assembled into the package cog."""

    def _trivia_game(self, ctx):
        return self.trivia_games.get(getattr(ctx.channel, "id", 0))

    @commands.command(name="trivia")
    async def trivia(self, ctx, category: str = ""):
        """a trivia question, optionally by category. usage: .trivia [category]"""
        category = category.strip().lower()
        if category and category not in CATEGORIES:
            return await ctx.warn("categories: " + ", ".join(f"`{name}`" for name in CATEGORIES))

        pool = [row for row in QUESTIONS if not category or row[2] == category]
        question, answers, topic = random.choice(pool)
        self.trivia_games[getattr(ctx.channel, "id", 0)] = {
            "question": question,
            "answers": [normalise(answer) for answer in answers],
            "display": answers[0],
            "category": topic,
            "tries": 0,
            "asked": time.time(),
        }
        await ctx.send(f"### trivia · {topic}\n{question}\n`.answer <text>`")

    @commands.command(name="answer", aliases=["ans"])
    async def answer(self, ctx, *, text: str = ""):
        """answer the trivia question. usage: .answer tokyo"""
        game = self._trivia_game(ctx)
        if not game:
            return await ctx.warn("no question running. `.trivia` to start one.")

        guess = normalise(text)
        if not guess:
            return await ctx.warn("usage: `.answer <text>`")

        if guess in game["answers"]:
            self.trivia_games.pop(getattr(ctx.channel, "id", 0), None)
            return await ctx.approve(f"**{game['display'].title()}** — correct.")

        game["tries"] += 1
        if game["tries"] >= MAX_TRIES:
            self.trivia_games.pop(getattr(ctx.channel, "id", 0), None)
            return await ctx.deny(
                f"out of tries — the answer was **{game['display'].title()}**."
            )
        await ctx.warn(f"not it. **{MAX_TRIES - game['tries']}** tries left.")
