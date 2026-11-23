"""Public, keyless lookups and two local tools (colour and time).

Every command answers with a short plain-text block and a readable failure: a
dead API says which API failed, never a traceback. Requests reuse the engine's
shared aiohttp session (:func:`core.api.session`) instead of opening one per
command.
"""
from __future__ import annotations

import asyncio
import colorsys
import re
from datetime import datetime, timezone as dt_timezone
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from discord.ext import commands

from core import api, prefs

USER_AGENT = "chrm-selfbot (https://github.com/Chrxmaticc/chrm)"

COINS = {
    "btc": "bitcoin", "bitcoin": "bitcoin",
    "eth": "ethereum", "ethereum": "ethereum",
    "sol": "solana", "solana": "solana",
    "doge": "dogecoin", "dogecoin": "dogecoin",
    "xrp": "ripple", "ripple": "ripple",
    "ada": "cardano", "cardano": "cardano",
    "ltc": "litecoin", "litecoin": "litecoin",
    "bnb": "binancecoin", "dot": "polkadot", "polkadot": "polkadot",
    "link": "chainlink", "chainlink": "chainlink",
    "avax": "avalanche-2", "avalanche": "avalanche-2",
    "matic": "matic-network", "polygon": "matic-network",
    "trx": "tron", "tron": "tron", "xmr": "monero", "monero": "monero",
    "ton": "the-open-network", "shib": "shiba-inu",
}

NAMED_COLORS = {
    "red": "#ff0000", "green": "#008000", "blue": "#0000ff", "pink": "#ffc0cb",
    "purple": "#800080", "orange": "#ffa500", "yellow": "#ffff00",
    "black": "#000000", "white": "#ffffff", "gray": "#808080", "grey": "#808080",
    "cyan": "#00ffff", "magenta": "#ff00ff", "lime": "#00ff00", "teal": "#008080",
    "navy": "#000080", "maroon": "#800000", "olive": "#808000",
    "silver": "#c0c0c0", "gold": "#ffd700", "brown": "#8b4513",
}

#: nearest basic emoji for a swatch, by RGB distance
SWATCHES = [
    ((255, 0, 0), "🟥"), ((255, 165, 0), "🟧"), ((255, 255, 0), "🟨"),
    ((0, 128, 0), "🟩"), ((0, 0, 255), "🟦"), ((128, 0, 128), "🟪"),
    ((0, 0, 0), "⬛"), ((255, 255, 255), "⬜"), ((139, 69, 19), "🟫"),
]

MAX_FIELD = 900


async def fetch_json(url: str, **params):
    """``(data, error)`` from a public JSON endpoint."""
    try:
        async with api.session().get(
            url, params=params or None, headers={"User-Agent": USER_AGENT}
        ) as response:
            if response.status == 404:
                return None, "not found"
            if response.status == 429:
                return None, "rate limited, try again in a minute"
            if response.status != 200:
                return None, f"http {response.status}"
            return await response.json(content_type=None), None
    except asyncio.TimeoutError:
        return None, "the api timed out"
    except Exception as exc:  # noqa: BLE001 - never traceback into a command
        return None, f"{type(exc).__name__}: {exc}"


def clean(text: str, limit: int = MAX_FIELD) -> str:
    text = re.sub(r"\[|\]", "", str(text)).replace("\r", "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def number(value: float) -> str:
    return f"{value:,.0f}" if abs(value) >= 1000 else f"{value:,.2f}".rstrip("0").rstrip(".")


def price(value: float) -> str:
    """Crypto prices keep their cents even above 1,000."""
    return f"{value:,.2f}".rstrip("0").rstrip(".")


def nearest_swatch(rgb) -> str:
    return min(SWATCHES, key=lambda pair: sum((a - b) ** 2 for a, b in zip(pair[0], rgb)))[1]


class WebLookupsMixin:
    """Commands for this sub-cog; assembled into the package cog."""

    # ------------------------------------------------------------ dictionary
    @commands.command(name="define", aliases=["dict", "dictionary"])
    async def define(self, ctx, *, word: str = ""):
        """dictionary definition. usage: .define serendipity"""
        word = word.strip()
        if not word:
            return await ctx.warn("usage: `.define <word>`")
        data, error = await fetch_json(
            f"https://api.dictionaryapi.dev/api/v2/entries/en/{quote(word)}"
        )
        if error or not isinstance(data, list) or not data:
            return await ctx.deny(f"no definition for **{word}**" + (f" ({error})" if error else "."))

        entry = data[0]
        lines = [f"### {entry.get('word', word)}"]
        phonetic = entry.get("phonetic") or next(
            (item.get("text") for item in entry.get("phonetics", []) if item.get("text")), ""
        )
        if phonetic:
            lines.append(phonetic)
        for meaning in entry.get("meanings", [])[:2]:
            lines.append(f"**{meaning.get('partOfSpeech', '—')}**")
            for definition in meaning.get("definitions", [])[:2]:
                lines.append(f"• {clean(definition.get('definition', ''), 240)}")
        await ctx.send("\n".join(lines))

    @commands.command(name="urban", aliases=["ud"])
    async def urban(self, ctx, *, term: str = ""):
        """urban dictionary lookup. usage: .urban ghosting"""
        term = term.strip()
        if not term:
            return await ctx.warn("usage: `.urban <term>`")
        data, error = await fetch_json(
            "https://api.urbandictionary.com/v0/define", term=term
        )
        entries = (data or {}).get("list") or []
        if error or not entries:
            return await ctx.deny(f"nothing for **{term}**" + (f" ({error})" if error else "."))

        lines = [f"### {term}"]
        for entry in entries[:2]:
            lines.append(clean(entry.get("definition", ""), 380))
            example = clean(entry.get("example", ""), 180)
            if example:
                lines.append(f"-# {example}")
        await ctx.send("\n".join(lines))

    # ------------------------------------------------------------ weather
    @commands.command(name="weather")
    async def weather(self, ctx, *, city: str = ""):
        """current weather for a city. usage: .weather london"""
        city = city.strip()
        if not city:
            return await ctx.warn("usage: `.weather <city>`")
        data, error = await fetch_json(f"https://wttr.in/{quote(city)}", format="j1")
        current = (data or {}).get("current_condition")
        if error or not current:
            return await ctx.deny(f"couldn't get weather for **{city}**" + (f" ({error})" if error else "."))

        now = current[0]
        area = ""
        try:
            area = data["nearest_area"][0]["areaName"][0]["value"]
        except (KeyError, IndexError, TypeError):
            pass
        description = (now.get("weatherDesc") or [{}])[0].get("value", "")
        await ctx.send(
            f"### {area or city}\n"
            f"**{now.get('temp_C')}°C** / {now.get('temp_F')}°F · {description}\n"
            f"feels **{now.get('FeelsLikeC')}°C** · humidity **{now.get('humidity')}%** · "
            f"wind **{now.get('windspeedKmph')} km/h**"
        )

    # ------------------------------------------------------------ dev lookups
    @commands.command(name="github", aliases=["gh"])
    async def github(self, ctx, *, target: str = ""):
        """github user or repo. usage: .github torvalds | .github owner/repo"""
        target = target.strip().strip("/").removeprefix("https://github.com/")
        if not target:
            return await ctx.warn("usage: `.github <user | owner/repo>`")

        if "/" in target:
            owner, repo = target.split("/", 1)
            data, error = await fetch_json(f"https://api.github.com/repos/{quote(owner)}/{quote(repo)}")
            if error or not data:
                return await ctx.deny(f"no repo **{target}**" + (f" ({error})" if error else "."))
            await ctx.send(
                f"### {data.get('full_name')}\n"
                f"{clean(data.get('description') or 'no description', 200)}\n"
                f"⭐ **{number(data.get('stargazers_count', 0))}** · "
                f"forks **{number(data.get('forks_count', 0))}** · "
                f"issues **{number(data.get('open_issues_count', 0))}**\n"
                f"language **{data.get('language') or '—'}** · "
                f"license **{(data.get('license') or {}).get('spdx_id') or '—'}**"
            )
            return

        data, error = await fetch_json(f"https://api.github.com/users/{quote(target)}")
        if error or not data:
            return await ctx.deny(f"no user **{target}**" + (f" ({error})" if error else "."))
        await ctx.send(
            f"### {data.get('login')} {data.get('name') or ''}\n"
            f"{clean(data.get('bio') or 'no bio', 200)}\n"
            f"repos **{data.get('public_repos', 0)}** · followers **{number(data.get('followers', 0))}** · "
            f"following **{data.get('following', 0)}**\n"
            f"[profile]({data.get('html_url')})"
        )

    @commands.command(name="npm")
    async def npm(self, ctx, *, package: str = ""):
        """npm package info. usage: .npm express"""
        package = package.strip()
        if not package:
            return await ctx.warn("usage: `.npm <package>`")
        data, error = await fetch_json(
            f"https://registry.npmjs.org/{quote(package, safe='@')}/latest"
        )
        if error or not data:
            return await ctx.deny(f"no npm package **{package}**" + (f" ({error})" if error else "."))
        await ctx.send(
            f"### {data.get('name')} `{data.get('version')}`\n"
            f"{clean(data.get('description') or 'no description', 240)}\n"
            f"license **{data.get('license') or '—'}** · "
            f"[npm](https://www.npmjs.com/package/{data.get('name')})"
        )

    @commands.command(name="pypi")
    async def pypi(self, ctx, *, package: str = ""):
        """pypi package info. usage: .pypi requests"""
        package = package.strip()
        if not package:
            return await ctx.warn("usage: `.pypi <package>`")
        data, error = await fetch_json(f"https://pypi.org/pypi/{quote(package)}/json")
        info = (data or {}).get("info")
        if error or not info:
            return await ctx.deny(f"no pypi package **{package}**" + (f" ({error})" if error else "."))
        await ctx.send(
            f"### {info.get('name')} `{info.get('version')}`\n"
            f"{clean(info.get('summary') or 'no summary', 240)}\n"
            f"python **{info.get('requires_python') or '—'}** · "
            f"license **{info.get('license') or '—'}**\n"
            f"[pypi]({info.get('package_url')})"
        )

    @commands.command(name="mcserver", aliases=["mcstatus"])
    async def mcserver(self, ctx, *, host: str = ""):
        """minecraft server status. usage: .mcserver play.hypixel.net"""
        host = host.strip()
        if not host:
            return await ctx.warn("usage: `.mcserver <host[:port]>`")
        data, error = await fetch_json(f"https://api.mcsrvstat.us/3/{quote(host)}")
        if error or not data:
            return await ctx.deny(f"couldn't check **{host}**" + (f" ({error})" if error else "."))

        if not data.get("online"):
            return await ctx.send(f"**{host}** is offline.")
        motd = " ".join(data.get("motd", {}).get("clean", []))
        players = data.get("players", {}) or {}
        await ctx.send(
            f"### {host} · online\n"
            f"{clean(motd, 200)}\n"
            f"players **{players.get('online', 0)}/{players.get('max', 0)}** · "
            f"version **{data.get('version') or '—'}**"
        )

    # ------------------------------------------------------------ crypto
    @commands.command(name="crypto", aliases=["price"])
    async def crypto(self, ctx, coin: str = "", currency: str = "usd"):
        """coin price. usage: .crypto btc [usd|eur|gbp]"""
        coin = coin.strip().lower()
        if not coin:
            return await ctx.warn("usage: `.crypto <coin> [usd|eur|gbp]`")
        ident = COINS.get(coin, coin)
        data, error = await fetch_json(
            "https://api.coingecko.com/api/v3/simple/price",
            ids=ident,
            vs_currencies=currency.lower(),
            include_24hr_change="true",
        )
        if error or not data or ident not in data:
            return await ctx.deny(
                f"no price for **{coin}**" + (f" ({error})" if error else " — try btc, eth, sol, doge…")
            )
        pair = data[ident]
        currency = currency.lower()
        value = pair.get(currency)
        change = pair.get(f"{currency}_24h_change")
        if value is None:
            return await ctx.warn(f"**{ident}** has no **{currency.upper()}** pair.")
        line = f"**{ident}** {price(value)} {currency.upper()}"
        if change is not None:
            line += f" · 24h **{change:+.2f}%**"
        await ctx.send(line)

    # ------------------------------------------------------------ ip
    @commands.command(name="ipinfo", aliases=["iplookup"])
    async def ipinfo(self, ctx, *, address: str = ""):
        """where an ip is. usage: .ipinfo 1.1.1.1"""
        address = address.strip()
        if not address:
            return await ctx.warn("usage: `.ipinfo <ip>`")
        data, error = await fetch_json(
            f"http://ip-api.com/json/{quote(address)}",
            fields="status,message,country,regionName,city,isp,org,timezone,query",
        )
        if error:
            return await ctx.deny(f"lookup failed ({error})")
        if not data or data.get("status") != "success":
            return await ctx.deny(f"couldn't look up **{address}**.")
        await ctx.send(
            f"### {data.get('query')}\n"
            f"{data.get('city')}, {data.get('regionName')}, {data.get('country')}\n"
            f"isp **{data.get('isp') or '—'}** · org **{data.get('org') or '—'}**\n"
            f"timezone **{data.get('timezone') or '—'}**"
        )

    # ------------------------------------------------------------ local tools
    @commands.command(name="color", aliases=["colour"])
    async def color(self, ctx, *, value: str = ""):
        """hex, rgb or a colour name. usage: .color #ff8800"""
        value = value.strip().lower()
        if not value:
            return await ctx.warn("usage: `.color #ff8800 | rgb(255,136,0) | orange`")

        value = NAMED_COLORS.get(value, value)
        rgb = None
        match = re.fullmatch(r"#?([0-9a-f]{3}|[0-9a-f]{6})", value)
        if match:
            digits = match.group(1)
            if len(digits) == 3:
                digits = "".join(char * 2 for char in digits)
            rgb = tuple(int(digits[index:index + 2], 16) for index in (0, 2, 4))
        else:
            numbers = [int(part) for part in re.findall(r"\d+", value)][:3]
            if len(numbers) == 3 and all(0 <= part <= 255 for part in numbers):
                rgb = tuple(numbers)
        if rgb is None:
            return await ctx.warn("that is not a colour. try `#ff8800`, `rgb(255,136,0)` or `orange`.")

        red, green, blue = rgb
        hue, lightness, saturation = colorsys.rgb_to_hls(red / 255, green / 255, blue / 255)
        await ctx.send(
            f"### {nearest_swatch(rgb)} #{red:02x}{green:02x}{blue:02x}\n"
            f"rgb **{red}, {green}, {blue}** · int **{red << 16 | green << 8 | blue}**\n"
            f"hsl **{hue * 360:.0f}°, {saturation * 100:.0f}%, {lightness * 100:.0f}%** · "
            f"luminance **{(0.2126 * red + 0.7152 * green + 0.0722 * blue) / 255:.2f}**"
        )

    @commands.command(name="time", aliases=["clock"])
    async def time(self, ctx, *, zone: str = ""):
        """current time somewhere. usage: .time | .time Europe/London"""
        name = zone.strip() or prefs.get(self.bot, "timezone", "UTC")
        try:
            here = ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError):
            return await ctx.warn(f"unknown timezone `{name}`. try `Europe/London` or `America/New_York`.")
        now = datetime.now(dt_timezone.utc).astimezone(here)
        offset = now.utcoffset()
        hours = int(offset.total_seconds() // 3600)
        minutes = int(abs(offset.total_seconds()) % 3600 // 60)
        await ctx.send(
            f"**{name}** · {now.strftime('%H:%M')} on {now.strftime('%A %d %B')}\n"
            f"utc{hours:+03d}:{minutes:02d} · <t:{int(now.timestamp())}:t> · <t:{int(now.timestamp())}:R>"
        )
