"""Content: the text banks and the two commands that talk back (``.poll``, ``.timer``).

Keeping the writing apart from the wiring means the catalogue stays a readable
table, and adding a joke is a one-line edit here rather than a code change.
"""
from __future__ import annotations

import random
import re

from plugins.levels.base import usage

JOKES = [
    "why do programmers prefer dark mode? because light attracts bugs.",
    "i told my computer i needed a break, and it said \"no problem, i'll go to sleep.\"",
    "there are two hard things in computer science: cache invalidation, naming things, and off-by-one errors.",
    "why did the developer go broke? because he used up all his cache.",
    "a sql query walks into a bar, approaches two tables and asks: may i join you?",
    "i would tell you a udp joke, but you might not get it.",
    "why do java developers wear glasses? because they don't c#.",
    "my code doesn't have bugs, it has randomly generated features.",
    "i changed my password to \"incorrect\". now windows tells me my password is incorrect.",
    "why was the javascript developer sad? because he didn't know how to null his feelings.",
    "the best thing about a boolean is that even if you are wrong, you are only off by a bit.",
    "i don't always test my code, but when i do, i do it in production.",
]

FACTS = [
    "honey never spoils — 3,000-year-old jars are still edible.",
    "octopuses have three hearts and blue blood.",
    "a day on venus is longer than a year on venus.",
    "sharks existed before trees.",
    "the eiffel tower grows about 15 cm taller in summer.",
    "bananas are berries, strawberries are not.",
    "there are more trees on earth than stars in the milky way.",
    "your stomach gets a new lining every few days, otherwise it would digest itself.",
    "a group of flamingos is called a flamboyance.",
    "wombat poop is cube-shaped.",
    "the first computer bug was a literal moth, taped into a logbook in 1947.",
    "discord was originally built around the idea of a \"chat for gamers\" called fates forever.",
]

QUOTES = [
    "the quieter you become, the more you can hear.",
    "you do not rise to the level of your goals, you fall to the level of your systems.",
    "done is better than perfect.",
    "if it is worth doing, it is worth doing badly at first.",
    "the best time to start was yesterday. the next best time is now.",
    "you will never be younger than you are right now.",
    "comparison is the thief of joy.",
    "people will forget what you said, but never how you made them feel.",
    "a goal without a plan is just a wish.",
    "everything you want is on the other side of a little bit of discomfort.",
]

TRUTHS = [
    "what is the last thing you searched for and hoped nobody would see?",
    "who in this chat would you trust with your password?",
    "what is the most embarrassing thing you have done for money?",
    "what is one thing you pretend not to care about but really do?",
    "what is the pettiest reason you have ever stopped talking to someone?",
    "what is your most useless talent?",
    "what is the biggest lie you have told in the last week?",
    "whose message do you reread the most?",
    "what is the last thing you deleted before sending?",
    "what is a compliment you have never forgotten?",
]

DARES = [
    "type your next message with your eyes closed.",
    "send the 5th photo in your camera roll.",
    "voice memo a dramatic reading of the last message in this chat.",
    "change your status to something embarrassing for 10 minutes.",
    "reply to the next message with only emojis.",
    "type with your non-dominant hand for the next 5 messages.",
    "say something genuinely nice about the last person who annoyed you.",
    "send a message in all caps and refuse to explain.",
    "use only song lyrics for the next 10 minutes.",
    "rename yourself to something cursed until someone notices.",
]

WYR = [
    "have unlimited money but never travel, or travel anywhere for free but stay broke?",
    "always be 10 minutes late, or always 30 minutes early?",
    "lose all your photos, or all your music?",
    "know how you die, or know when?",
    "have a rewind button for conversations, or a mute button for people?",
    "never use social media again, or never watch another show?",
    "be the funniest person in the room, or the smartest?",
    "fight one horse-sized duck, or 100 duck-sized horses?",
    "read every thought people have about you, or have everyone read yours?",
    "have perfect memory, or be able to forget anything on command?",
]

PICKUP = [
    "are you a discord ping? because you have my full attention.",
    "do you have a map? i keep getting lost in your messages.",
    "are you wifi? because i feel a connection.",
    "you must be a compiler, because you just made my heart run.",
    "if you were a function, you would be my favourite — no side effects, all return.",
    "are you a 404? because i keep looking for you.",
    "you are the semicolon to my statement: everything falls apart without you.",
    "i would say you are out of my league, but i do not play games i cannot win.",
    "are you an exception? because i would catch you every time.",
    "you had me at \"read receipt\".",
]

FORTUNES = [
    "a suspiciously good day is coming. do not question it.",
    "someone is thinking about you right now. it is probably your bank.",
    "you will find what you lost in the last place you look. obviously.",
    "big win soon, but the small ones matter more.",
    "the reply you are waiting for arrives when you stop refreshing.",
    "you will be unexpectedly right about something this week.",
    "an old friend will message you. answer faster than last time.",
    "the thing you are avoiding takes 10 minutes. start it.",
    "you will be the reason someone has a good day. no pressure.",
    "a boring choice turns out to be the right one.",
    "you will sleep too late and still be fine.",
    "the next thing you download will be worth it. probably.",
]

EXCUSES = [
    "my cat walked across the keyboard and closed the tab.",
    "i was compiling my thoughts and the build failed.",
    "my wifi briefly entered another dimension.",
    "i had to restart my router, my pc, and my will to live.",
    "i was reading the docs. all of them. twice.",
    "i was on mute. in real life.",
    "my alarm clock and i had a disagreement.",
    "i was waiting for the message to load and it never did. classic.",
    "my phone died at the exact worst moment, as is tradition.",
    "i was busy doing the thing i said i would do yesterday.",
]

SHOWERTHOUGHTS = [
    "your phone knows more about your sleep than your family does.",
    "we call it a \"password\" but everyone shares it with their family.",
    "\"saving\" a post is just bookmarks with extra steps and no follow-through.",
    "the \"reply all\" button has started more wars than most governments.",
    "you have never seen your own face in real life, only reflections and photos.",
    "every group chat has one person who only replies with reactions.",
    "the internet made it possible to be lonely in front of 5,000 people.",
    "naps are just free trials of death.",
    "you are the oldest you have ever been and the youngest you will ever be again.",
    "typing \"lol\" when you did not laugh is the polite lie of our generation.",
]

COMPLIMENTS = [
    "{b}, your taste is genuinely unmatched.",
    "{b}, you make this chat better just by showing up.",
    "{b}, you are the kind of person people remember.",
    "{b}, your brain works in a way that is honestly cool.",
    "{b}, you are way more capable than you give yourself credit for.",
    "{b}, you have great instincts. trust them.",
]

ROASTS = [
    "{b}, your search history is the reason your ads are like that.",
    "{b}, you have the confidence of someone who has never read the error message.",
    "{b}, you are the human equivalent of a 200 response with an empty body.",
    "{b}, your code runs and nobody knows why. including you.",
    "{b}, you type like autocorrect gave up halfway.",
    "{b}, you are not the sharpest tool in the shed, but you are definitely the loudest.",
]

HYPE = [
    "🔥 **{text}** 🔥",
    "LET'S GOOO — **{text}**",
    "📣 **{text}** 📣 📣 📣",
    "on god, **{text}** is happening.",
]

SLAP = ["{a} slaps {b} around a bit with a large trout.",
        "{a} winds up and slaps {b} clean across the channel.",
        "{a} delivers a perfectly timed slap to {b}."]
HUG = ["{a} hugs {b} tightly.",
       "{a} wraps {b} in a warm, entirely consensual hug.",
       "{a} gives {b} the kind of hug that fixes a bad day."]
PAT = ["{a} pats {b} on the head.",
       "{a} gives {b} three very deliberate pats.",
       "{a} pats {b}. good job, {b}."]
BONK = ["{a} bonks {b} on the head. back to horny jail.",
        "{a} delivers a decisive bonk to {b}.",
        "{a} bonks {b} with the authority of a disappointed parent."]
KISS = ["{a} kisses {b} on the forehead.",
        "{a} throws a kiss at {b}. catch.",
        "{a} kisses {b} dramatically, like a soap opera ending."]
HIGHFIVE = ["{a} high-fives {b}. clean contact.",
            "{a} and {b} high-five so hard the channel shakes.",
            "{a} high-fives {b} and immediately regrets it."]
CONGRATS = ["{a} congratulates {b}. well deserved.",
            "{b} did the thing. {a} is proud.",
            "round of applause for {b}, from {a}."]
SIMP = ["{a} is down bad for {b}.",
        "{a} would fold immediately for {b}.",
        "{a} has a whole folder dedicated to {b}. it is not subtle."]


def hype(cog, ctx, arg):
    text = (arg or "").strip()
    if not text:
        return usage("usage: `.hype <text>`")
    return random.choice(HYPE).format(text=text.upper())


def topic(cog, ctx, arg):
    line = random.choice(SHOWERTHOUGHTS)
    return f"🚿 **shower thought** — {line}"


KEYCAP = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣"]


async def poll(cog, ctx, arg):
    """Send the poll, then react with the numbers so people can actually vote."""
    parts = [part.strip() for part in (arg or "").split("|")]
    question = parts[0] if parts else ""
    options = [part for part in parts[1:] if part][:9]
    if not question or len(options) < 2:
        return usage("usage: `.poll question | option one | option two`")
    lines = [f"📊 **{question}**", ""] + [f"{KEYCAP[i]} {option}" for i, option in enumerate(options)]
    message = await ctx.send("\n".join(lines))
    for emoji in KEYCAP[:len(options)]:
        try:
            await message.add_reaction(emoji)
        except Exception as exc:  # noqa: BLE001 - a reaction failing must not kill the poll
            print(f"[levels] poll reaction failed: {exc}")
            break
    return None


_DURATION = re.compile(r"(\d+(?:\.\d+)?)\s*(s|sec|secs|m|min|mins|h|hr|hrs|d|day|days)", re.I)
_UNITS = {"s": 1, "sec": 1, "secs": 1, "m": 60, "min": 60, "mins": 60,
          "h": 3600, "hr": 3600, "hrs": 3600, "d": 86400, "day": 86400, "days": 86400}


def parse_duration(text: str):
    total = 0.0
    found = False
    for value, unit in _DURATION.findall(text or ""):
        total += float(value) * _UNITS[unit.lower()]
        found = True
    if not found:
        return None
    return max(1, int(total))


def pretty_duration(seconds: int) -> str:
    if seconds % 86400 == 0:
        return f"{seconds // 86400}d"
    if seconds % 3600 == 0:
        return f"{seconds // 3600}h"
    if seconds % 60 == 0:
        return f"{seconds // 60}m"
    return f"{seconds}s"


def timer(cog, ctx, arg):
    match = _DURATION.search(arg or "")
    if not match:
        return usage("usage: `.timer 10m <what to remind you about>`")
    seconds = parse_duration(match.group(0))
    note = (arg or "")[match.end():].strip() or "timer done."
    if not seconds:
        return usage("usage: `.timer 10m <what to remind you about>`")
    if seconds > 7 * 86400:
        return usage("keep it under 7 days — `.schedule` exists for the long stuff.")
    cog.start_timer(seconds, note, ctx.channel, getattr(ctx, "author", None))
    return f"⏱ timer set for **{pretty_duration(seconds)}** — {note}"
