"""Reference lookups: images, Wikipedia, books, words, money, sky and news.

Everything here is keyless and public. Pinterest is deliberately absent from the
image path: it refuses datacenter IPs, which is exactly what a Render box is, so
``.image`` goes to Openverse first and Wikimedia Commons second. Both answer a
cloud host without an account.

Every command answers with a short plain-text block and a readable failure: a
dead API says which API failed, never a traceback. Requests go through
:mod:`core.web`, which reuses the engine's shared aiohttp session.
"""
from __future__ import annotations

import asyncio
import html
import re
import time
from datetime import date, datetime, timezone as dt_timezone
from urllib.parse import quote

from discord.ext import commands

from core import web

MAX_FIELD = 900

WIKI_REST = "https://en.wikipedia.org/api/rest_v1"
WIKI_API = "https://en.wikipedia.org/w/api.php"
WIKI_PAGE = "https://en.wikipedia.org/wiki/"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"

#: two-letter codes for the holiday API; names are friendlier than codes
COUNTRY_CODES = {
    "uk": "GB", "gb": "GB", "britain": "GB", "england": "GB",
    "us": "US", "usa": "US", "america": "US", "canada": "CA", "ca": "CA",
    "australia": "AU", "au": "AU", "ireland": "IE", "ie": "IE",
    "france": "FR", "fr": "FR", "germany": "DE", "de": "DE",
    "spain": "ES", "es": "ES", "italy": "IT", "it": "IT",
    "portugal": "PT", "pt": "PT", "netherlands": "NL", "nl": "NL",
    "belgium": "BE", "be": "BE", "switzerland": "CH", "ch": "CH",
    "austria": "AT", "at": "AT", "sweden": "SE", "se": "SE",
    "norway": "NO", "no": "NO", "denmark": "DK", "dk": "DK",
    "finland": "FI", "fi": "FI", "poland": "PL", "pl": "PL",
    "czechia": "CZ", "czech": "CZ", "cz": "CZ", "greece": "GR", "gr": "GR",
    "japan": "JP", "jp": "JP", "south korea": "KR", "korea": "KR", "kr": "KR",
    "india": "IN", "in": "IN", "brazil": "BR", "br": "BR",
    "mexico": "MX", "mx": "MX", "argentina": "AR", "ar": "AR",
    "south africa": "ZA", "za": "ZA", "new zealand": "NZ", "nz": "NZ",
    "russia": "RU", "ru": "RU", "turkey": "TR", "tr": "TR",
}


def clip(text, limit: int = 240) -> str:
    """One line, collapsed whitespace, never longer than ``limit``."""
    value = " ".join(str(text or "").split())
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def strip_tags(text) -> str:
    """Wikipedia snippets arrive as HTML fragments."""
    return clip(html.unescape(re.sub(r"<[^>]+>", "", str(text or ""))), 200)


def number(value) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "0"


def split_count(raw: str, default: int = 4, maximum: int = 6):
    """``"cozy desk -n 2"`` -> ``("cozy desk", 2)``; a bad ``-n`` is ignored."""
    words = []
    count = default
    tokens = raw.split()
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if (
            token in ("-n", "--n", "--count")
            and index + 1 < len(tokens)
            and tokens[index + 1].isdigit()
        ):
            count = max(1, min(int(tokens[index + 1]), maximum))
            index += 2
            continue
        words.append(token)
        index += 1
    return " ".join(words).strip(), count


async def commons_images(query: str, count: int):
    """``[(title, url)]`` from Wikimedia Commons search, or ``([], error)``."""
    data, error = await web.fetch_json(
        COMMONS_API,
        action="query",
        generator="search",
        gsrsearch=query,
        gsrnamespace="6",
        gsrlimit=str(count),
        prop="imageinfo",
        iiprop="url",
        iiurlwidth="900",
        format="json",
    )
    pages = ((data or {}).get("query") or {}).get("pages") or {}
    hits = []
    for page in pages.values():
        info = (page.get("imageinfo") or [{}])[0]
        link = info.get("url")
        if link:
            hits.append((str(page.get("title") or "file").removeprefix("File:"), link))
    return hits, error


def moment(stamp) -> str:
    """Discord's ``<t:...:R>`` for a unix timestamp, or an em dash."""
    try:
        return f"<t:{int(stamp)}:R>"
    except (TypeError, ValueError):
        return "—"


class ReferenceMixin:
    """Commands for this sub-cog; assembled into the package cog."""

    # ------------------------------------------------------------ images
    @commands.command(name="image", aliases=["images", "img"])
    async def image(self, ctx, *, query: str = ""):
        """image search, no pinterest. usage: .image cozy desk [-n 4]"""
        query, count = split_count(query)
        if not query:
            return await ctx.warn("usage: `.image <query> [-n 4]`")

        data, error = await web.fetch_json(
            "https://api.openverse.org/v1/images/", q=query, page_size=str(count)
        )
        hits = [
            (item.get("title") or "untitled", item.get("url"), item.get("creator") or "")
            for item in (data or {}).get("results") or []
            if item.get("url")
        ]
        source = "openverse"
        if not hits:
            commons, commons_error = await commons_images(query, count)
            hits = [(title, link, "") for title, link in commons]
            source = "wikimedia commons"
            error = error or commons_error
        if not hits:
            return await ctx.deny(f"no images for **{clip(query, 60)}**" + (f" ({error})" if error else "."))

        lines = [f"### images · {clip(query, 60)}"]
        for title, link, creator in hits[:count]:
            heading = clip(title, 70)
            if creator:
                heading += f" — {clip(creator, 40)}"
            lines.append(f"**{heading}**\n{link}")
        lines.append(f"-# via {source}")
        await ctx.send("\n".join(lines))

    # ------------------------------------------------------------ wikipedia
    @commands.command(name="wiki", aliases=["wikipedia"])
    async def wiki(self, ctx, *, topic: str = ""):
        """wikipedia summary. usage: .wiki dune novel"""
        topic = topic.strip()
        if not topic:
            return await ctx.warn("usage: `.wiki <topic>`")
        slug = quote(topic.replace(" ", "_"), safe="")
        data, error = await web.fetch_json(f"{WIKI_REST}/page/summary/{slug}")
        if error or not data or not data.get("extract"):
            return await ctx.deny(
                f"no wikipedia page for **{clip(topic, 60)}**" + (f" ({error})" if error else ".")
            )

        lines = [f"### {data.get('title', topic)}"]
        if data.get("description"):
            lines.append(f"-# {clip(data.get('description'), 120)}")
        lines.append(clip(data.get("extract"), 700))
        if data.get("type") == "disambiguation":
            lines.append("-# this is a disambiguation page — try a more specific title")
        link = ((data.get("content_urls") or {}).get("desktop") or {}).get("page")
        if link:
            lines.append(f"[read on wikipedia]({link})")
        await ctx.send("\n".join(lines))

    @commands.command(name="wikisearch", aliases=["wsearch"])
    async def wikisearch(self, ctx, *, query: str = ""):
        """search wikipedia titles. usage: .wikisearch dune"""
        query = query.strip()
        if not query:
            return await ctx.warn("usage: `.wikisearch <query>`")
        data, error = await web.fetch_json(
            WIKI_API,
            action="query",
            list="search",
            srsearch=query,
            srlimit="5",
            format="json",
        )
        hits = ((data or {}).get("query") or {}).get("search") or []
        if error or not hits:
            return await ctx.deny(f"nothing on wikipedia for **{clip(query, 60)}**" + (f" ({error})" if error else "."))

        lines = [f"### wikipedia · {clip(query, 60)}"]
        for hit in hits:
            title = hit.get("title") or "untitled"
            link = WIKI_PAGE + quote(title.replace(" ", "_"), safe="")
            lines.append(f"**[{clip(title, 70)}]({link})**\n-# {strip_tags(hit.get('snippet'))}")
        await ctx.send("\n".join(lines))

    @commands.command(name="randomwiki", aliases=["rwiki"])
    async def randomwiki(self, ctx):
        """a random wikipedia article. usage: .randomwiki"""
        data, error = await web.fetch_json(f"{WIKI_REST}/page/random/summary")
        if error or not data or not data.get("extract"):
            return await ctx.deny(f"wikipedia didn't answer ({error or 'empty page'})")

        lines = [f"### {data.get('title', 'random article')}"]
        if data.get("description"):
            lines.append(f"-# {clip(data.get('description'), 120)}")
        lines.append(clip(data.get("extract"), 600))
        link = ((data.get("content_urls") or {}).get("desktop") or {}).get("page")
        if link:
            lines.append(f"[read on wikipedia]({link})")
        await ctx.send("\n".join(lines))

    @commands.command(name="onthisday", aliases=["otd"])
    async def onthisday(self, ctx):
        """what happened today in history. usage: .onthisday"""
        now = datetime.now(dt_timezone.utc)
        data, error = await web.fetch_json(
            f"{WIKI_REST}/feed/onthisday/events/{now.month:02d}/{now.day:02d}"
        )
        events = (data or {}).get("events") or []
        if error or not events:
            return await ctx.deny(f"wikipedia didn't answer ({error or 'no events'})")

        events.sort(key=lambda item: item.get("year") or 0)
        lines = [f"### on this day · {now.strftime('%d %B')}"]
        for event in events[:6]:
            lines.append(f"**{event.get('year', '—')}** · {clip(event.get('text'), 150)}")
        await ctx.send("\n".join(lines))

    # ------------------------------------------------------------ books
    @commands.command(name="book", aliases=["books", "openlibrary"])
    async def book(self, ctx, *, query: str = ""):
        """search open library. usage: .book dune"""
        query = query.strip()
        if not query:
            return await ctx.warn("usage: `.book <title or author>`")
        data, error = await web.fetch_json(
            "https://openlibrary.org/search.json",
            q=query,
            limit="5",
            fields="title,author_name,first_publish_year,key,edition_count",
        )
        docs = (data or {}).get("docs") or []
        if error or not docs:
            return await ctx.deny(f"no books for **{clip(query, 60)}**" + (f" ({error})" if error else "."))

        lines = [f"### books · {clip(query, 60)}"]
        for doc in docs[:5]:
            authors = ", ".join((doc.get("author_name") or [])[:2]) or "unknown author"
            year = doc.get("first_publish_year")
            link = "https://openlibrary.org" + str(doc.get("key") or "")
            editions = doc.get("edition_count") or 0
            lines.append(
                f"**[{clip(doc.get('title'), 70)}]({link})** — {clip(authors, 60)}"
                + (f" ({year})" if year else "")
                + f"\n-# {number(editions)} editions"
            )
        await ctx.send("\n".join(lines))

    # ------------------------------------------------------------ words
    async def _words_like(self, ctx, word: str, rel: str, heading: str, hint: str, name: str):
        word = word.strip()
        if not word:
            return await ctx.warn(f"usage: `.{name} <word>`")
        data, error = await web.fetch_json("https://api.datamuse.com/words", **{rel: word, "max": "8"})
        words = [item.get("word") for item in (data or []) if item.get("word")]
        if error or not words:
            return await ctx.deny(f"{hint} for **{clip(word, 40)}**" + (f" ({error})" if error else "."))
        await ctx.send(f"### {heading} · {word}\n" + " · ".join(words))

    @commands.command(name="rhyme", aliases=["rhymes"])
    async def rhyme(self, ctx, *, word: str = ""):
        """words that rhyme. usage: .rhyme time"""
        await self._words_like(ctx, word, "rel_rhy", "rhymes", "no rhymes", "rhyme")

    @commands.command(name="synonym", aliases=["syn", "synonyms"])
    async def synonym(self, ctx, *, word: str = ""):
        """words that mean the same. usage: .synonym happy"""
        await self._words_like(ctx, word, "rel_syn", "synonyms", "no synonyms", "synonym")

    @commands.command(name="antonym", aliases=["ant", "antonyms"])
    async def antonym(self, ctx, *, word: str = ""):
        """words that mean the opposite. usage: .antonym happy"""
        await self._words_like(ctx, word, "rel_ant", "antonyms", "no antonyms", "antonym")

    # ------------------------------------------------------------ news
    @commands.command(name="hn", aliases=["hackernews"])
    async def hn(self, ctx):
        """hacker news front page. usage: .hn"""
        data, error = await web.fetch_json("https://hacker-news.firebaseio.com/v0/topstories.json")
        ids = [int(item) for item in (data or []) if str(item).isdigit()][:5]
        if error or not ids:
            return await ctx.deny(f"hacker news didn't answer ({error or 'empty list'})")

        results = await asyncio.gather(
            *(web.fetch_json(f"https://hacker-news.firebaseio.com/v0/item/{ident}.json") for ident in ids)
        )
        lines = ["### hacker news"]
        for rank, (item, item_error) in enumerate(results, 1):
            if not item:
                continue
            link = item.get("url") or f"https://news.ycombinator.com/item?id={item.get('id')}"
            comments = f"https://news.ycombinator.com/item?id={item.get('id')}"
            lines.append(
                f"**{rank}.** [{clip(item.get('title'), 110)}]({link})\n"
                f"-# ▲ {item.get('score', 0)} · 💬 {item.get('descendants', 0)} · [comments]({comments})"
            )
        if len(lines) == 1:
            return await ctx.deny("hacker news sent nothing readable.")
        await ctx.send("\n".join(lines))

    # ------------------------------------------------------------ money
    @commands.command(name="currency", aliases=["fx", "exchange"])
    async def currency(self, ctx, *, args: str = ""):
        """convert money. usage: .currency 100 usd eur | .currency usd gbp"""
        tokens = args.split()
        amount = 1.0
        if len(tokens) == 3:
            try:
                amount = float(tokens.pop(0).replace(",", ""))
            except ValueError:
                return await ctx.warn("usage: `.currency [amount] <from> <to>`")
        if len(tokens) != 2:
            return await ctx.warn("usage: `.currency 100 usd eur`")

        base, target = tokens[0].upper(), tokens[1].upper()
        data, error = await web.fetch_json(
            "https://api.frankfurter.dev/v1/latest", base=base, symbols=target
        )
        rate = ((data or {}).get("rates") or {}).get(target)
        if error or rate is None:
            return await ctx.deny(
                f"couldn't convert **{base}** to **{target}**" + (f" ({error})" if error else ".")
            )
        await ctx.send(
            f"**{amount:,.2f} {base}** = **{amount * rate:,.2f} {target}**\n"
            f"-# 1 {base} = {rate:.4f} {target} · {data.get('date', '—')} · frankfurter"
        )

    # ------------------------------------------------------------ sky
    @commands.command(name="sun", aliases=["sunrise", "sunset"])
    async def sun(self, ctx, *, city: str = ""):
        """sunrise and sunset. usage: .sun london"""
        city = city.strip()
        if not city:
            return await ctx.warn("usage: `.sun <city>`")
        geo, error = await web.fetch_json(
            "https://geocoding-api.open-meteo.com/v1/search", name=city, count="1"
        )
        places = (geo or {}).get("results") or []
        if error or not places:
            return await ctx.deny(f"couldn't find **{clip(city, 40)}**" + (f" ({error})" if error else "."))

        place = places[0]
        data, error = await web.fetch_json(
            "https://api.sunrise-sunset.org/json",
            lat=place.get("latitude"),
            lng=place.get("longitude"),
            formatted="0",
        )
        results = (data or {}).get("results") or {}
        sunrise, sunset = results.get("sunrise"), results.get("sunset")
        if error or not sunrise or not sunset:
            return await ctx.deny(f"sun times didn't answer ({error or 'no times'})")

        try:
            rise = datetime.fromisoformat(str(sunrise).replace("Z", "+00:00"))
            down = datetime.fromisoformat(str(sunset).replace("Z", "+00:00"))
        except ValueError:
            return await ctx.deny("that api sent times I can't read.")

        seconds = int(results.get("day_length") or (down - rise).total_seconds())
        hours, rest = divmod(max(0, seconds), 3600)
        minutes = rest // 60
        label = ", ".join(str(part) for part in (place.get("name"), place.get("country")) if part)
        await ctx.send(
            f"### sun · {label}\n"
            f"sunrise <t:{int(rise.timestamp())}:t> · sunset <t:{int(down.timestamp())}:t> · "
            f"daylight **{hours}h {minutes}m**\n"
            f"-# local times · now <t:{int(time.time())}:R>"
        )

    @commands.command(name="iss", aliases=["spacestation"])
    async def iss(self, ctx):
        """where the space station is. usage: .iss"""
        data, error = await web.fetch_json("http://api.open-notify.org/iss-now.json")
        position = (data or {}).get("iss_position") or {}
        lat, lon = position.get("latitude"), position.get("longitude")
        if error or lat is None or lon is None:
            return await ctx.deny(f"couldn't locate the iss ({error or 'no position'})")
        await ctx.send(
            f"### iss · now\nlatitude **{lat}** · longitude **{lon}**\n"
            f"-# {moment((data or {}).get('timestamp'))} · "
            f"[map](https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=3/{lat}/{lon})"
        )

    @commands.command(name="earthquake", aliases=["quake", "quakes"])
    async def earthquake(self, ctx):
        """quakes above 4.5 in the last day. usage: .earthquake"""
        data, error = await web.fetch_json(
            "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_day.geojson"
        )
        features = (data or {}).get("features") or []
        if error:
            return await ctx.deny(f"usgs didn't answer ({error})")
        if not features:
            return await ctx.send("no quakes at **4.5+** in the last day.")

        features.sort(key=lambda item: (item.get("properties") or {}).get("mag") or 0, reverse=True)
        lines = ["### earthquakes · 4.5+ · last 24h"]
        for feature in features[:5]:
            props = feature.get("properties") or {}
            lines.append(
                f"**M {props.get('mag', '—')}** — {clip(props.get('place') or 'somewhere', 80)} · "
                f"{moment((props.get('time') or 0) / 1000)}\n{props.get('url', '')}"
            )
        await ctx.send("\n".join(lines))

    # ------------------------------------------------------------ misc
    @commands.command(name="holidays", aliases=["holiday"])
    async def holidays(self, ctx, country: str = "", year: str = ""):
        """public holidays by country. usage: .holidays gb | .holidays us 2027"""
        country = country.strip()
        if not country:
            return await ctx.warn("usage: `.holidays <country code|name> [year]`")
        code = COUNTRY_CODES.get(country.lower(), country.upper())
        if len(code) != 2 or not code.isalpha():
            return await ctx.warn("use a two-letter code or a country name, like `.holidays gb`.")

        today = datetime.now(dt_timezone.utc).date()
        if year:
            if not year.isdigit() or not 1970 <= int(year) <= 2100:
                return await ctx.warn("that isn't a year I can ask about.")
            target_year = int(year)
        else:
            target_year = today.year

        data, error = await web.fetch_json(
            f"https://date.nager.at/api/v3/PublicHolidays/{target_year}/{code}"
        )
        if error or data is None:
            return await ctx.deny(f"no holidays for **{code}**" + (f" ({error})" if error else "."))
        entries = []
        for entry in data or []:
            try:
                when = date.fromisoformat(str(entry.get("date")))
            except ValueError:
                continue
            if year or when >= today:
                entries.append((when, entry))
        if not entries:
            return await ctx.send(
                f"no more public holidays in **{code}** for {target_year} — try `.holidays {code} {target_year + 1}`."
            )

        entries.sort(key=lambda pair: pair[0])
        lines = [f"### holidays · {code} · {target_year}"]
        for when, entry in entries[:10]:
            lines.append(f"**{when.strftime('%d %b')}** · {clip(entry.get('localName') or entry.get('name'), 70)}")
        await ctx.send("\n".join(lines))

    @commands.command(name="qr", aliases=["qrcode"])
    async def qr(self, ctx, *, text: str = ""):
        """a qr code link for any text. usage: .qr https://example.com"""
        text = text.strip()
        if not text:
            return await ctx.warn("usage: `.qr <text or url>`")
        link = (
            "https://api.qrserver.com/v1/create-qr-code/?size=400x400&data="
            + quote(clip(text, 400), safe="")
        )
        await ctx.send(f"### qr\n{link}")

    @commands.command(name="crates", aliases=["crate"])
    async def crates(self, ctx, *, name: str = ""):
        """rust crate info. usage: .crates serde"""
        name = name.strip()
        if not name:
            return await ctx.warn("usage: `.crates <crate>`")
        data, error = await web.fetch_json(f"https://crates.io/api/v1/crates/{quote(name)}")
        crate = (data or {}).get("crate") or {}
        if error or not crate:
            return await ctx.deny(f"no crate **{clip(name, 40)}**" + (f" ({error})" if error else "."))
        versions = (data or {}).get("versions") or []
        latest = (versions[0] or {}).get("num") if versions else None
        latest = latest or crate.get("max_version") or "—"
        await ctx.send(
            f"### {crate.get('name')} `{latest}`\n"
            f"{clip(crate.get('description') or 'no description', 220)}\n"
            f"downloads **{number(crate.get('downloads'))}** · "
            f"[crates.io](https://crates.io/crates/{crate.get('name')})"
        )
