""".pinterest`` -- pins, boards and people straight off pinterest.com.

The site's own web endpoints answer without an API key (see ``helpers.py``), so
this needs no configuration at all. It is read-only: saving, following and
commenting would all need a logged-in session cookie, which is exactly the kind
of credential a selfbot should not be trusted with.

Output is text by design. ``discord.py-self`` exposes no ``embed`` parameter on
``send``/``edit`` (a user account cannot attach rich embeds), so each pin is a
title, a stats line and the bare ``i.pinimg.com`` URL -- Discord turns that
link into the image preview itself.
"""
import asyncio
import random
from urllib.parse import quote

import discord
from discord.ext import commands

from .helpers import PAGE_SIZE, Pinterest, PinterestError, board, board_hit, pin, profile, user_hit

#: Discord rejects anything longer; leave room for the header and a newline.
MESSAGE_LIMIT = 1900

#: Discord previews ten links per message well enough; also the `-n` ceiling.
MAX_PINS = 10

#: pins per command when `-n` is not given -- "some images", not a wall of them.
DEFAULT_PINS = 3

MODES = ("board", "pins", "user", "boards", "people", "random")

#: `.pinterest random` draws from these; they are searches that always resolve.
RANDOM_QUERIES = (
    "emo",
    "grunge aesthetic",
    "y2k",
    "dark academia",
    "cybercore",
    "liminal space",
    "vaporwave",
    "coquette",
    "goth",
    "film grain",
)

USAGE = (
    "`.pinterest <query> [-n 3]` — pins that match\n"
    "`.pinterest board <user>/<board> [-n 3]` — pins from one board\n"
    "`.pinterest pins <user> [-n 3]` — a random handful of someone's pins\n"
    "`.pinterest user <name>` — profile card (followers, pins, boards)\n"
    "`.pinterest boards <query>` — boards that match\n"
    "`.pinterest people <query>` — accounts that match\n"
    "`.pinterest random` — a random aesthetic search"
)


def _esc(value):
    return discord.utils.escape_markdown(str(value or ""))


def _clip(value, limit):
    """One line, no newlines, and never longer than a title line wants."""
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _count(value):
    return f"{value:,}" if isinstance(value, int) else ""


def _meta(*bits):
    return " · ".join(bit for bit in bits if bit)


def parse_args(raw):
    """``"[board] target [-n 4]"`` -> ``{'mode', 'target', 'count'}``.

    Returns ``None`` when ``-n`` has no number after it, so the caller can say
    so instead of quietly searching for the literal text ``-n``.
    """
    tokens = raw.split()
    count = DEFAULT_PINS
    words = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token in ("-n", "--n", "--count"):
            if index + 1 >= len(tokens) or not tokens[index + 1].lstrip("-").isdigit():
                return None
            count = int(tokens[index + 1])
            index += 2
            continue
        if token.startswith("-n") and token[2:].isdigit():
            count = int(token[2:])
            index += 1
            continue
        words.append(token)
        index += 1

    count = max(1, min(count, MAX_PINS))
    if not words:
        return {"mode": "help", "target": "", "count": count}

    mode = words[0].lower()
    if mode in MODES:
        return {"mode": mode, "target": " ".join(words[1:]).strip(), "count": count}
    return {"mode": "search", "target": " ".join(words).strip(), "count": count}


def pin_block(item):
    """One pin: title, a short description, its counts, then the image itself."""
    title = item["title"] or item["board"]["name"] or "pinterest pin"
    lines = [f"**{_clip(_esc(title), 120)}**"]

    description = item["description"]
    if description and description != item["title"]:
        lines.append(_clip(_esc(description), 160))

    board_name = item["board"]["name"]
    board_link = f"[{_esc(board_name)}]({item['board']['url']})" if item["board"]["url"] else _esc(board_name)
    lines.append(
        "-# "
        + _meta(
            f"{item['saves']:,} saves" if item["saves"] is not None else "",
            f"{item['likes']:,} likes" if item["likes"] else "",
            f"in {board_link}" if board_name else "",
            _esc(item["domain"]),
        )
    )
    if item["image"]:
        lines.append(item["image"])
    return "\n".join(line for line in lines if line and line != "-# ")


def profile_block(card):
    """A Pinterest account as a few lines."""
    handle = f" (@{_esc(card['username'])})" if card["username"] else ""
    lines = [f"📌 **{_clip(_esc(card['name']), 120)}**{handle}"]
    if card["about"]:
        lines.append(_clip(_esc(card["about"]), 200))
    lines.append(
        "-# "
        + _meta(
            f"{card['followers']:,} followers" if card["followers"] is not None else "",
            f"{card['following']:,} following" if card["following"] is not None else "",
            f"{card['pins']:,} pins" if card["pins"] is not None else "",
            f"{card['boards']:,} boards" if card["boards"] is not None else "",
            f"[profile]({card['url']})" if card["url"] else "",
            _esc(card["website"]),
        )
    )
    return "\n".join(lines)


def board_header(card, searched):
    head = f"📌 **{_clip(_esc(card['name']), 120)}**" if card else f"📌 **board** `{_esc(searched)}`"
    meta = []
    if card:
        if card["pins"] is not None:
            meta.append(f"{card['pins']:,} pins")
        if card["followers"] is not None:
            meta.append(f"{card['followers']:,} followers")
        if card["owner"]:
            meta.append(f"by {_esc(card['owner'])}")
        if card["url"]:
            meta.append(f"[open on pinterest]({card['url']})")
    return head + (f"\n-# {_meta(*meta)}" if meta else "")


def render_boards(items, query):
    lines = [f"📌 **boards for** `{_esc(query)}`"]
    if not items:
        lines.append("no boards matched that.")
    for rank, hit in enumerate(items[:10], start=1):
        name = _esc(hit["name"]) or "untitled"
        if hit["url"]:
            name = f"[{name}]({hit['url']})"
        meta = _meta(
            f"{hit['pins']:,} pins" if hit["pins"] is not None else "",
            f"{hit['followers']:,} followers" if hit["followers"] is not None else "",
            f"by {_esc(hit['owner'])}" if hit["owner"] else "",
        )
        lines.append(f"`{rank:02d}` {name}" + (f" · {meta}" if meta else ""))
    lines.append(
        f"-# [open on pinterest](https://www.pinterest.com/search/boards/?q={quote(query)})"
    )
    return "\n".join(lines)


def render_people(items, query):
    lines = [f"📌 **people for** `{_esc(query)}`"]
    if not items:
        lines.append("no accounts matched that.")
    for rank, hit in enumerate(items[:10], start=1):
        name = _esc(hit["name"]) or _esc(hit["username"])
        link = f"[{name}]({hit['url']})" if hit["url"] else name
        meta = _meta(
            f"@{_esc(hit['username'])}" if hit["username"] else "",
            f"{hit['followers']:,} followers" if hit["followers"] is not None else "",
            f"{hit['pins']:,} pins" if hit["pins"] is not None else "",
        )
        lines.append(f"`{rank:02d}` {link}" + (f" · {meta}" if meta else ""))
    lines.append(
        f"-# [open on pinterest](https://www.pinterest.com/search/users/?q={quote(query)})"
    )
    return "\n".join(lines)


def chunk(header, blocks, limit=MESSAGE_LIMIT):
    """Split a header plus pin blocks into messages that fit Discord's cap."""
    messages = []
    current = header
    for block in blocks:
        candidate = f"{current}\n\n{block}" if current else block
        if len(candidate) > limit and current:
            messages.append(current)
            current = block
        else:
            current = candidate
    if current:
        messages.append(current)
    return messages


class PinterestMixin:
    """Commands for this sub-cog; assembled into the package cog."""

    def _pinterest_client(self):
        """One long-lived session: the csrf cookie is worth keeping between calls."""
        client = getattr(self, "_pinterest_session", None)
        if client is None or client.session.closed:
            client = Pinterest.open()
            self._pinterest_session = client
        return client

    def cog_unload_pinterest(self):
        client = getattr(self, "_pinterest_session", None)
        if client is not None and not client.session.closed:
            asyncio.create_task(client.close())
        self._pinterest_session = None

    # -- individual modes -------------------------------------------------------
    async def _pinterest_pins(self, client, query, count, seed=False):
        items, _ = await client.search_pins(query, PAGE_SIZE)
        pool = [pin(item) for item in items if item.get("images")]
        picked = random.sample(pool, min(count, len(pool))) if pool else []
        if not picked:
            raise PinterestError(f"no pins matched `{query}`.")

        label = "random pins for" if seed else "pins for"
        header = (
            f"📌 **{label}** `{_esc(query)}`\n"
            f"-# [search](https://www.pinterest.com/search/pins/?q={quote(query)})"
        )
        return header, [pin_block(item) for item in picked]

    async def _pinterest_board(self, client, target, count):
        username, slug = target.strip("/").split("/", 1)
        if not username or not slug:
            raise PinterestError("a board is `<user>/<board>`, both parts needed.")

        try:
            card = board(await client.board(username, slug))
        except PinterestError:
            # the feed below is what actually matters; a missing card is cosmetic
            card = None

        items, _ = await client.board_feed(username, slug, PAGE_SIZE)
        pool = [pin(item) for item in items if item.get("images")]
        picked = random.sample(pool, min(count, len(pool))) if pool else []
        if not picked:
            raise PinterestError(f"`{username}/{slug}` has no pins to show.")

        return board_header(card, target), [pin_block(item) for item in picked]

    async def _pinterest_user_pins(self, client, username, count):
        items, _ = await client.user_pins(username, PAGE_SIZE)
        pool = [pin(item) for item in items if item.get("images")]
        picked = random.sample(pool, min(count, len(pool))) if pool else []
        if not picked:
            raise PinterestError(f"`{username}` has no pins to show.")
        return f"📌 **pins from** @{_esc(username)}", [pin_block(item) for item in picked]

    async def _pinterest_run(self, client, args):
        mode, target, count = args["mode"], args["target"], args["count"]

        if mode == "search":
            if not target:
                raise PinterestError("usage: `.pinterest <query>` — e.g. `.pinterest emo`.")
            return await self._pinterest_pins(client, target, count)

        if mode == "random":
            return await self._pinterest_pins(client, random.choice(RANDOM_QUERIES), count, seed=True)

        if mode == "board":
            if "/" not in target.strip("/"):
                raise PinterestError(
                    "usage: `.pinterest board <user>/<board>` — "
                    "e.g. `.pinterest board pinterest/official-news`."
                )
            return await self._pinterest_board(client, target, count)

        if mode == "pins":
            if not target:
                raise PinterestError("usage: `.pinterest pins <user>`.")
            return await self._pinterest_user_pins(client, target.lstrip("@"), count)

        if mode == "user":
            if not target:
                raise PinterestError("usage: `.pinterest user <name>`.")
            return profile_block(profile(await client.profile(target.lstrip("@")))), []

        if mode == "boards":
            if not target:
                raise PinterestError("usage: `.pinterest boards <query>`.")
            items, _ = await client.search_boards(target, PAGE_SIZE)
            return render_boards([board_hit(item) for item in items], target), []

        if mode == "people":
            if not target:
                raise PinterestError("usage: `.pinterest people <query>`.")
            items, _ = await client.search_users(target, PAGE_SIZE)
            return render_people([user_hit(item) for item in items], target), []

        raise PinterestError("that mode isn't one I know.")

    @commands.command(name="pinterest")
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def pinterest(self, ctx, *, query: str = ""):
        """pinterest pins, boards and profiles. usage: .pinterest <query> | .pinterest board <user>/<board> | .pinterest user <name>"""
        error = self.bot.config.get_emoji("error")
        loading = self.bot.config.get_emoji("loading")

        args = parse_args(query)
        if args is None:
            return await ctx.send(f"{error} `-n` needs a number, like `.pinterest emo -n 3`.")
        if args["mode"] == "help":
            return await ctx.send(USAGE)

        target = args["target"] or args["mode"]
        msg = await ctx.send(f"{loading} searching pinterest for `{_esc(target)}`...")
        try:
            header, blocks = await self._pinterest_run(self._pinterest_client(), args)
        except PinterestError as exc:
            return await msg.edit(content=f"{error} {exc}")

        messages = chunk(header, blocks)
        await msg.edit(content=messages[0])
        for extra in messages[1:]:
            await ctx.send(extra)
