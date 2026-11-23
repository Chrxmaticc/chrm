"""Discord's detectable-games catalogue: name, app id, icon hash, aliases.

``cdn.phaseworld.top`` used to serve a scraped copy of this and now answers 404,
which is why ``.fakeplay`` lost its icons and ``.farmtime`` reported an empty
database. Discord ships the same list itself:

* ``https://cdn.discordapp.com/detectables/games.json`` -- 13MB, cached for an
  hour, ``access-control-allow-origin: *``;
* ``https://discord.com/api/v10/applications/detectable`` -- byte-identical,
  unauthenticated, kept as the fallback.

The icon hash in that file is the whole point: with it, every game's official art
is one CDN URL away and no per-game API request is needed.

The file holds 100k+ applications, so :func:`parse` does not call ``json.loads``
on it. It walks the array one object at a time with ``raw_decode`` and keeps only
the four fields above, which keeps peak memory near the download size instead of
several times it. That matters: the engine is killed at ~460MB RSS.
"""
import json
from typing import NamedTuple

SOURCE = "https://cdn.discordapp.com/detectables/games.json"
FALLBACK = "https://discord.com/api/v10/applications/detectable"

#: the CDN form ``ActivityAssets`` rewrites to ``mp:app-icons/...``
CDN_ICON = "https://cdn.discordapp.com/app-icons/{app_id}/{icon}.png"

HEADERS = {"User-Agent": "chrm/1.0 (+https://github.com/Chrxmaticc/chrm)"}

#: skip the whitespace and commas between array entries
_SEPARATORS = " \t\r\n,"

#: abbreviations the catalogue does not list as aliases, so fuzzy matching would
#: pick the wrong title (``cs2`` otherwise finds the game literally called CS2D)
PREFERRED = {
    "cs2": "Counter-Strike 2",
    "csgo": "Counter-Strike: Global Offensive",
    "css": "Counter-Strike: Source",
    "gta": "Grand Theft Auto V Enhanced",
    "gta5": "Grand Theft Auto V Enhanced",
}


class Game(NamedTuple):
    """One detectable application."""

    name: str
    app_id: str
    icon_hash: str = ""
    aliases: tuple = ()


def parse(text):
    """Parse the games array without materialising the whole document."""
    games = []
    decoder = json.JSONDecoder()
    index = text.find("[")
    if index < 0:
        return games
    index += 1
    length = len(text)
    while index < length:
        while index < length and text[index] in _SEPARATORS:
            index += 1
        if index >= length or text[index] == "]":
            break
        try:
            entry, index = decoder.raw_decode(text, index)
        except ValueError:
            break
        if not isinstance(entry, dict):
            continue
        app_id = str(entry.get("id") or "")
        name = entry.get("name") or ""
        if not app_id.isdigit() or not name:
            continue
        aliases = entry.get("aliases") or []
        games.append(
            Game(
                str(name),
                app_id,
                str(entry.get("icon_hash") or ""),
                tuple(str(alias).strip().lower() for alias in aliases if alias),
            )
        )
    return games


async def download(session, url=SOURCE, timeout=90):
    """Fetch and parse one catalogue URL."""
    async with session.get(url, headers=HEADERS, timeout=timeout) as resp:
        if resp.status != 200:
            raise RuntimeError(f"{url} -> HTTP {resp.status}")
        text = await resp.text()
    try:
        return parse(text)
    finally:
        del text


async def load(session, primary=SOURCE, fallback=FALLBACK):
    """Load the catalogue, trying the CDN first and the API endpoint second."""
    problems = []
    for url in (primary, fallback):
        if not url:
            continue
        try:
            games = await download(session, url)
        except Exception as exc:  # noqa: BLE001 - report every source we tried
            problems.append(f"{url}: {type(exc).__name__}: {exc}")
            continue
        if games:
            return games
        problems.append(f"{url}: parsed to nothing")
    raise RuntimeError("; ".join(problems) or "no catalogue URL")


def icon_url(game):
    """The official icon for a game, or ``None`` when it has no hash."""
    if not game or not game.icon_hash:
        return None
    return CDN_ICON.format(app_id=game.app_id, icon=game.icon_hash)


def find(games, query):
    """Best match for ``query``: exact name, alias, prefix, then substring."""
    wanted = (query or "").strip().lower()
    if not wanted:
        return None

    preferred = PREFERRED.get(wanted)
    if preferred:
        for game in games:
            if game.name == preferred:
                return game

    alias_hit = prefix_hit = substring_hit = None
    for game in games:
        name = game.name.lower()
        if name == wanted:
            return game
        if alias_hit is None and wanted in game.aliases:
            alias_hit = game
        if prefix_hit is None and name.startswith(wanted):
            prefix_hit = game
        if substring_hit is None and wanted in name:
            substring_hit = game
    return alias_hit or prefix_hit or substring_hit
