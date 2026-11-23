"""Quick games: slots, blackjack, unscramble and a few conversation starters."""
from __future__ import annotations

import random
import re

from discord.ext import commands

from plugins.fun.extended.games.words import WORDS

REELS = ["🍒", "🍋", "🍇", "🔔", "💎", "7️⃣"]

NHIE = [
    "never have i ever stayed up until sunrise for no reason",
    "never have i ever pretended to be busy to avoid someone",
    "never have i ever deleted a message because of a typo",
    "never have i ever stalked someone's old posts",
    "never have i ever fallen asleep in a call",
    "never have i ever said \"i'm on my way\" while still in bed",
    "never have i ever cried at a movie",
    "never have i ever ghosted someone",
    "never have i ever lied about my age",
    "never have i ever pretended to like a gift",
    "never have i ever eaten food that fell on the floor",
    "never have i ever sent a message to the wrong chat",
    "never have i ever googled myself",
    "never have i ever skipped a whole day of messages",
    "never have i ever used a alt account to check on someone",
    "never have i ever been caught talking to myself",
    "never have i ever faked being sick",
    "never have i ever forgotten a close friend's birthday",
    "never have i ever sang badly on purpose",
    "never have i ever taken a selfie in a bathroom",
]

TOPICS = [
    "what is one skill you want to learn this year?",
    "what is the best purchase you have ever made?",
    "what is a movie you can rewatch forever?",
    "what is the worst food combination you actually like?",
    "what is a small thing that instantly ruins your mood?",
    "what was your first username online?",
    "what is the last song you had on repeat?",
    "what is a hill you will die on?",
    "what is the nicest thing a stranger has done for you?",
    "what is your most useless talent?",
    "what is a trend you are glad is over?",
    "what would you do with a free day and no phone?",
    "what is the best compliment you have received?",
    "what is a game you wish you could play again for the first time?",
    "what is your comfort show?",
    "what is the most spontaneous thing you have done?",
    "what is a thing you own that has no value to anyone else?",
    "what is your go-to late night snack?",
    "what is a place you want to visit before you die?",
    "what is the pettiest reason you have disliked someone?",
]

SUITS = ["♠", "♥", "♦", "♣"]
RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]


def hand_value(hand) -> int:
    """Best blackjack total: aces count 11 until that would bust."""
    total = sum(11 if rank == "A" else 10 if rank in ("J", "Q", "K") else int(rank) for rank, _ in hand)
    aces = sum(1 for rank, _ in hand if rank == "A")
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total


def hand_text(hand, hide_first: bool = False) -> str:
    cards = [("??" if hide_first and index == 0 else f"{rank}{suit}") for index, (rank, suit) in enumerate(hand)]
    total = hand_value(hand)
    shown = "?" if hide_first else str(total)
    return f"{' '.join(cards)} ({shown})"


def new_deck() -> list:
    deck = [(rank, suit) for suit in SUITS for rank in RANKS]
    random.shuffle(deck)
    return deck


class GamesMixin:
    """Commands for this sub-cog; assembled into the package cog."""

    # ------------------------------------------------------------ slots
    @commands.command(name="slots")
    async def slots(self, ctx):
        """spin three reels. usage: .slots"""
        reels = [random.choice(REELS) for _ in range(3)]
        if reels == ["7️⃣", "7️⃣", "7️⃣"]:
            verdict = "jackpot. the house is filing for bankruptcy."
        elif len(set(reels)) == 1:
            verdict = "three of a kind — big win."
        elif len(set(reels)) == 2:
            verdict = "two matching — small win."
        else:
            verdict = "nothing. the house thanks you."
        await ctx.send(f"### slots\n{' '.join(reels)}\n{verdict}")

    # ------------------------------------------------------------ blackjack
    def _blackjack_game(self, ctx):
        return self.blackjack_games.get(getattr(ctx.channel, "id", 0))

    def _blackjack_board(self, game, reveal: bool = False) -> str:
        lines = [
            "### blackjack",
            f"**you** {hand_text(game['player'])}",
            f"**dealer** {hand_text(game['dealer'], hide_first=not reveal)}",
        ]
        if reveal:
            player, dealer = hand_value(game["player"]), hand_value(game["dealer"])
            if player > 21:
                lines.append("you busted.")
            elif dealer > 21:
                lines.append("dealer busted — you win.")
            elif player > dealer:
                lines.append("you win.")
            elif player == dealer:
                lines.append("push.")
            else:
                lines.append("dealer wins.")
        else:
            lines.append("`.hit` or `.stand`")
        return "\n".join(lines)

    @commands.command(name="blackjack", aliases=["bj", "21"])
    async def blackjack(self, ctx):
        """start a hand of blackjack. usage: .blackjack"""
        current = self._blackjack_game(ctx)
        if current:
            return await ctx.send(self._blackjack_board(current))

        deck = new_deck()
        game = {"deck": deck, "player": [deck.pop(), deck.pop()], "dealer": [deck.pop(), deck.pop()]}
        self.blackjack_games[getattr(ctx.channel, "id", 0)] = game

        board = self._blackjack_board(game)
        if hand_value(game["player"]) == 21:
            self.blackjack_games.pop(getattr(ctx.channel, "id", 0), None)
            return await ctx.send(f"{board}\nblackjack — natural 21.")
        await ctx.send(board)

    @commands.command(name="hit")
    async def hit(self, ctx):
        """draw another card. usage: .hit"""
        game = self._blackjack_game(ctx)
        if not game:
            return await ctx.warn("no hand running. `.blackjack` to start one.")
        game["player"].append(game["deck"].pop())
        if hand_value(game["player"]) > 21:
            self.blackjack_games.pop(getattr(ctx.channel, "id", 0), None)
            return await ctx.send(self._blackjack_board(game, reveal=True))
        await ctx.send(self._blackjack_board(game))

    @commands.command(name="stand")
    async def stand(self, ctx):
        """stop drawing and let the dealer play. usage: .stand"""
        game = self._blackjack_game(ctx)
        if not game:
            return await ctx.warn("no hand running. `.blackjack` to start one.")
        while hand_value(game["dealer"]) < 17:
            game["dealer"].append(game["deck"].pop())
        self.blackjack_games.pop(getattr(ctx.channel, "id", 0), None)
        await ctx.send(self._blackjack_board(game, reveal=True))

    # ------------------------------------------------------------ unscramble
    def _scramble(self, ctx):
        return self.unscramble_games.get(getattr(ctx.channel, "id", 0))

    @commands.command(name="unscramble", aliases=["scramble"])
    async def unscramble(self, ctx):
        """unscramble a word. usage: .unscramble"""
        current = self._scramble(ctx)
        if current:
            return await ctx.send(f"still waiting on `{current['shown']}` — `.usolve <word>`.")

        word = random.choice(WORDS)
        letters = list(word)
        random.shuffle(letters)
        shown = "".join(letters)
        while shown == word:  # a swap that changes nothing is a bad puzzle
            random.shuffle(letters)
            shown = "".join(letters)
        self.unscramble_games[getattr(ctx.channel, "id", 0)] = {"word": word, "shown": shown}
        await ctx.send(f"### unscramble\n`{shown}` — {len(word)} letters. `.usolve <word>`")

    @commands.command(name="usolve")
    async def usolve(self, ctx, *, answer: str = ""):
        """answer the unscramble. usage: .usolve apple"""
        game = self._scramble(ctx)
        if not game:
            return await ctx.warn("no unscramble here. `.unscramble` to start one.")
        if answer.strip().lower() != game["word"]:
            return await ctx.warn("not it. look again.")
        self.unscramble_games.pop(getattr(ctx.channel, "id", 0), None)
        await ctx.approve(f"**{game['word']}** — solved.")

    # ------------------------------------------------------------ starters
    @commands.command(name="nhie")
    async def nhie(self, ctx):
        """never have i ever. usage: .nhie"""
        await ctx.send(f"**never have i ever** {random.choice(NHIE).replace('never have i ever ', '')}")

    @commands.command(name="topic")
    async def topic(self, ctx):
        """a conversation starter. usage: .topic"""
        await ctx.send(f"**topic** {random.choice(TOPICS)}")

    # ------------------------------------------------------------ text stats
    @commands.command(name="wordcount")
    async def wordcount(self, ctx, *, text: str = ""):
        """characters, words, sentences and reading time. usage: .wordcount <text>"""
        text = text.strip()
        if not text:
            return await ctx.warn("usage: `.wordcount <text>`")
        words = re.findall(r"[A-Za-z0-9']+", text)
        sentences = len(re.findall(r"[.!?]+", text)) or (1 if text else 0)
        lines = len(text.splitlines())
        longest = max(words, key=len) if words else "—"
        minutes = max(1, round(len(words) / 200)) if words else 0
        await ctx.send(
            "### text stats\n"
            f"**{len(text)}** characters · **{len(text.replace(' ', ''))}** without spaces\n"
            f"**{len(words)}** words · **{sentences}** sentences · **{lines}** lines\n"
            f"longest word **{longest}** · about **{minutes} min** to read"
        )
