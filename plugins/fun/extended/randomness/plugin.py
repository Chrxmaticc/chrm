"""Random picks: animal photos, jokes, quotes, a webcomic and a pokédex entry.

Same rules as the rest of the keyless lookups: no accounts, no keys, one
readable line when an API is down, and no image hosting of our own -- each
command returns the picture's direct URL so Discord unfurls it.
"""
from __future__ import annotations

from urllib.parse import quote

from discord.ext import commands

from core import web


def clip(text, limit: int = 300) -> str:
    value = " ".join(str(text or "").split())
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


class RandomnessMixin:
    """Commands for this sub-cog; assembled into the package cog."""

    # ------------------------------------------------------------ animals
    @commands.command(name="dog", aliases=["doggo", "puppy"])
    async def dog(self, ctx):
        """a random dog. usage: .dog"""
        data, error = await web.fetch_json("https://dog.ceo/api/breeds/image/random")
        link = (data or {}).get("message")
        if error or not link:
            return await ctx.deny(f"the dog api didn't answer ({error or 'no image'})")
        breed = ""
        if "/breeds/" in link:
            breed = link.split("/breeds/", 1)[1].split("/", 1)[0].replace("-", " ")
        await ctx.send(f"### dog{f' · {breed}' if breed else ''}\n{link}")

    @commands.command(name="cat", aliases=["kitty"])
    async def cat(self, ctx):
        """a random cat. usage: .cat"""
        data, error = await web.fetch_json("https://cataas.com/cat", json="true")
        link = (data or {}).get("url") if isinstance(data, dict) else None
        if link and link.startswith("/"):
            link = "https://cataas.com" + link
        if not link:
            fallback, fallback_error = await web.fetch_json("https://api.thecatapi.com/v1/images/search")
            link = ((fallback or [{}])[0] or {}).get("url") if isinstance(fallback, list) else None
            error = error or fallback_error
        if not link:
            return await ctx.deny(f"the cat api didn't answer ({error or 'no image'})")
        await ctx.send(f"### cat\n{link}")

    @commands.command(name="fox", aliases=["foxes"])
    async def fox(self, ctx):
        """a random fox. usage: .fox"""
        data, error = await web.fetch_json("https://randomfox.ca/floof/")
        link = (data or {}).get("image")
        if error or not link:
            return await ctx.deny(f"the fox api didn't answer ({error or 'no image'})")
        await ctx.send(f"### fox\n{link}")

    @commands.command(name="duck", aliases=["ducky"])
    async def duck(self, ctx):
        """a random duck. usage: .duck"""
        data, error = await web.fetch_json("https://random-d.uk/api/v2/quack")
        link = (data or {}).get("url")
        if error or not link:
            return await ctx.deny(f"the duck api didn't answer ({error or 'no image'})")
        await ctx.send(f"### duck\n{link.replace('http://', 'https://')}")

    # ------------------------------------------------------------ words
    @commands.command(name="joke", aliases=["dadjoke"])
    async def joke(self, ctx):
        """a dad joke. usage: .joke"""
        data, error = await web.fetch_json("https://icanhazdadjoke.com/")
        line = (data or {}).get("joke") if isinstance(data, dict) else None
        if error or not line:
            return await ctx.deny(f"the joke api didn't answer ({error or 'no joke'})")
        await ctx.send(f"### joke\n{clip(line, 400)}")

    @commands.command(name="quote", aliases=["quotes"])
    async def quote(self, ctx):
        """a random quote. usage: .quote"""
        data, error = await web.fetch_json("https://zenquotes.io/api/random")
        entry = (data or [{}])[0] if isinstance(data, list) and data else {}
        text, author = entry.get("q"), entry.get("a")
        if error or not text:
            return await ctx.deny(f"the quote api didn't answer ({error or 'no quote'})")
        await ctx.send(f"### quote\n“{clip(text, 400)}”\n-# {clip(author or 'unknown', 60)}")

    # ------------------------------------------------------------ comics
    @commands.command(name="xkcd")
    async def xkcd(self, ctx, number: str = ""):
        """an xkcd comic. usage: .xkcd | .xkcd 400"""
        target = number.strip().lstrip("#")
        if target and not target.isdigit():
            return await ctx.warn("usage: `.xkcd [number]`")
        url = (
            f"https://xkcd.com/{int(target)}/info.0.json"
            if target
            else "https://xkcd.com/info.0.json"
        )
        data, error = await web.fetch_json(url)
        if error or not data:
            return await ctx.deny(f"no comic **{target or 'today'}**" + (f" ({error})" if error else "."))
        lines = [f"### xkcd #{data.get('num', '?')} · {clip(data.get('title'), 80)}", str(data.get("img", ""))]
        alt = clip(data.get("alt"), 300)
        if alt:
            lines.append(f"-# {alt}")
        await ctx.send("\n".join(lines))

    # ------------------------------------------------------------ pokemon
    @commands.command(name="pokemon", aliases=["pokedex", "poke"])
    async def pokemon(self, ctx, *, name: str = ""):
        """pokédex entry. usage: .pokemon pikachu"""
        name = name.strip().lower()
        if not name:
            return await ctx.warn("usage: `.pokemon <name or number>`")
        data, error = await web.fetch_json(f"https://pokeapi.co/api/v2/pokemon/{quote(name)}")
        if error or not data or not data.get("name"):
            return await ctx.deny(f"no pokémon called **{clip(name, 40)}**" + (f" ({error})" if error else "."))

        types = ", ".join(
            entry.get("type", {}).get("name", "?") for entry in data.get("types") or []
        ) or "—"
        stats = {
            entry.get("stat", {}).get("name"): entry.get("base_stat")
            for entry in data.get("stats") or []
        }
        sprites = data.get("sprites") or {}
        art = ((sprites.get("other") or {}).get("official-artwork") or {}).get("front_default")
        art = art or sprites.get("front_default")
        lines = [
            f"### {data.get('name')} · #{int(data.get('id') or 0):03d}",
            f"types **{types}** · height **{(data.get('height') or 0) / 10:.1f} m** · "
            f"weight **{(data.get('weight') or 0) / 10:.1f} kg**",
            f"hp **{stats.get('hp', '—')}** · attack **{stats.get('attack', '—')}** · "
            f"defense **{stats.get('defense', '—')}** · speed **{stats.get('speed', '—')}**",
        ]
        if art:
            lines.append(art)
        await ctx.send("\n".join(lines))
