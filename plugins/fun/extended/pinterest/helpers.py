"""Pinterest lookups through the same web endpoints the site itself calls.

No API key, no account, nothing to configure: ``www.pinterest.com`` serves its
own JSON from ``/resource/<Name>/get/`` to any client that sends the headers its
web bundle sends. Two of those headers are load-bearing:

* ``x-pinterest-pws-handler`` and ``x-pinterest-source-url`` -- without them the
  endpoint answers ``403 Invalid Resource Request`` no matter how good the query
  or the cookies are;
* ``x-csrftoken`` -- copied out of the ``csrftoken`` cookie, which means every
  fresh session has to visit ``/`` once before its first resource call.

Three things the web API does not hand out, and this module does not pretend
otherwise: search results arrive without save/like counts (only profile and
board feeds carry ``aggregated_pin_data``), a saved pin's page is private to its
owner, and pins are addressed internally by long ``e1_...`` ids rather than the
numeric ones in a pin URL -- so a pin is linked to its source page or its board,
never to a guessed ``/pin/`` address.
"""
import base64
import json
import html
from email.utils import parsedate_to_datetime
from urllib.parse import quote

import aiohttp

BASE = "https://www.pinterest.com"

#: Pinterest serves a stripped page to unknown agents; this is a plain Chrome.
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

TIMEOUT = aiohttp.ClientTimeout(total=20)

#: page_size Pinterest accepts; anything bigger is silently clamped
PAGE_SIZE = 25


class PinterestError(Exception):
    """A lookup that failed in a way worth showing to the user."""


def _text(value):
    """Collapse Pinterest's whitespace and unescape ``&amp;``-style entities."""
    if value is None:
        return ""
    return " ".join(html.unescape(str(value)).split())


def _stamp(value):
    """``'Wed, 24 Mar 2021 01:24:30 +0000'`` -> unix seconds."""
    if not value:
        return None
    try:
        return int(parsedate_to_datetime(value).timestamp())
    except (TypeError, ValueError, OverflowError):
        return None


def _abs(url):
    """Board/pin URLs arrive relative (``/user/board/``)."""
    url = _text(url)
    if not url:
        return ""
    return url if url.startswith("http") else BASE + url


def _num(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _image(obj, *sizes):
    """First usable image URL, in the order the caller wants the sizes."""
    images = obj.get("images") or {}
    for size in sizes:
        url = _text((images.get(size) or {}).get("url"))
        if url:
            return url
    return ""


def numeric_id(pin_id):
    """Decode the ``node_id`` fallback: ``UGluOjEyMzQ=`` -> ``1234``.

    Pinterest's ids are base64 of ``Pin:<id>``; the numeric form is what older
    links use, so it is worth keeping even though nothing here fetches by it.
    """
    raw = _text(pin_id)
    if not raw:
        return ""
    try:
        decoded = base64.b64decode(raw + "=" * (-len(raw) % 4)).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return ""
    return decoded.split(":", 1)[-1]


class Pinterest:
    """One browsing session: a homepage visit for the csrf cookie, then JSON."""

    def __init__(self, session):
        self.session = session
        self._csrf = ""
        self._ready = False

    @classmethod
    def open(cls):
        """A client with its own cookie jar; the caller owns :meth:`close`."""
        session = aiohttp.ClientSession(
            headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}
        )
        return cls(session)

    async def close(self):
        await self.session.close()

    async def _home(self):
        try:
            async with self.session.get(f"{BASE}/", timeout=TIMEOUT) as resp:
                await resp.read()
        except aiohttp.ClientError as exc:
            raise PinterestError(
                f"couldn't reach pinterest ({exc.__class__.__name__})"
            )
        for cookie in self.session.cookie_jar:
            if cookie.key == "csrftoken":
                self._csrf = cookie.value
                break
        self._ready = True

    async def _resource(self, name, handler, options, source):
        if not self._ready:
            await self._home()

        data = json.dumps({"options": options, "context": {}})
        url = (
            f"{BASE}/resource/{name}/get/?source_url={quote(source)}"
            f"&data={quote(data)}"
        )
        headers = {
            "Accept": "application/json, text/javascript, */*, q=0.01",
            "Referer": BASE + source,
            "Origin": BASE,
            "x-pinterest-appstate": "active",
            "x-requested-with": "XMLHttpRequest",
            "x-pinterest-pws-handler": handler,
            "x-pinterest-source-url": source,
            "x-csrftoken": self._csrf,
        }
        try:
            async with self.session.get(url, headers=headers, timeout=TIMEOUT) as resp:
                status = resp.status
                body = await resp.text()
        except aiohttp.ClientError as exc:
            raise PinterestError(
                f"couldn't reach pinterest ({exc.__class__.__name__})"
            )

        if status == 403:
            if "Invalid Resource Request" in body:
                # the query/options combination Pinterest refuses, not our headers
                raise PinterestError("pinterest rejected that search, try another query")
            raise PinterestError("pinterest is blocking us right now, try again later")
        if status == 429:
            raise PinterestError("pinterest is rate limiting, try again in a minute")

        try:
            payload = json.loads(body)
        except ValueError:
            raise PinterestError(f"pinterest sent a non-json reply (http {status})")

        response = payload.get("resource_response") or {}
        error = response.get("error")
        if error:
            message = _text(error.get("message")) if isinstance(error, dict) else _text(error)
            raise PinterestError(message or f"pinterest returned http {status}")
        if status != 200:
            raise PinterestError(f"pinterest returned http {status}")

        return response.get("data"), response.get("bookmark")

    async def search_pins(self, query, limit=PAGE_SIZE):
        data, bookmark = await self._resource(
            "BaseSearchResource",
            "www/search/[scope].js",
            {
                "query": query,
                "scope": "pins",
                "page_size": limit,
                "redux_normalize_feed": True,
                "rs": "rs",
            },
            f"/search/pins/?q={quote(query)}&rs=typed",
        )
        return _items(data), bookmark

    async def search_boards(self, query, limit=PAGE_SIZE):
        data, bookmark = await self._resource(
            "BaseSearchResource",
            "www/search/[scope].js",
            {"query": query, "scope": "boards", "page_size": limit},
            f"/search/boards/?q={quote(query)}",
        )
        return _items(data), bookmark

    async def search_users(self, query, limit=PAGE_SIZE):
        data, bookmark = await self._resource(
            "BaseSearchResource",
            "www/search/[scope].js",
            {"query": query, "scope": "users", "page_size": limit},
            f"/search/users/?q={quote(query)}",
        )
        return _items(data), bookmark

    async def board_feed(self, username, slug, limit=PAGE_SIZE):
        data, bookmark = await self._resource(
            "BoardFeedResource",
            "www/[username]/[slug].js",
            {
                "board_id": f"{username}/{slug}",
                "field_set_key": "react_grid_pin",
                "page_size": limit,
            },
            f"/{username}/{slug}/",
        )
        return _items(data), bookmark

    async def user_pins(self, username, limit=PAGE_SIZE):
        data, bookmark = await self._resource(
            "UserPinsResource",
            "www/[username].js",
            {"username": username, "field_set_key": "grid_item", "page_size": limit},
            f"/{username}/pins/",
        )
        return _items(data), bookmark

    async def profile(self, username):
        data, _ = await self._resource(
            "UserResource",
            "www/[username].js",
            {"username": username, "field_set_key": "profile"},
            f"/{username}/",
        )
        if isinstance(data, dict) and data.get("username"):
            return data
        raise PinterestError(f"no pinterest account called `{username}`")

    async def board(self, username, slug):
        data, _ = await self._resource(
            "BoardResource",
            "www/[username]/[slug].js",
            {"slug": slug, "username": username, "field_set_key": "detailed"},
            f"/{username}/{slug}/",
        )
        if isinstance(data, dict) and data.get("name"):
            return data
        raise PinterestError(f"no board at `{username}/{slug}`")


def _items(data):
    if isinstance(data, dict):
        return list(data.get("results") or [])
    return list(data or [])


def pin(obj):
    """One feed item -> what the embed needs."""
    stats = (obj.get("aggregated_pin_data") or {}).get("aggregated_stats") or {}
    reactions = obj.get("reaction_counts") or {}
    likes = sum(v for v in reactions.values() if isinstance(v, int))
    board = obj.get("board") or {}
    pinner = obj.get("pinner") or {}
    return {
        "id": _text(obj.get("id")),
        "title": _text(obj.get("grid_title") or obj.get("title")),
        "description": _text(obj.get("description")),
        "image": _image(obj, "736x", "564x", "474x", "orig", "236x"),
        "saves": _num(stats.get("saves")),
        "likes": likes or None,
        "domain": _text(obj.get("domain")),
        "link": _text(obj.get("link")),
        "created": _stamp(obj.get("created_at")),
        "board": {
            "name": _text(board.get("name")),
            "url": _abs(board.get("url")),
        },
        "pinner": {
            "username": _text(pinner.get("username")),
            "name": _text(pinner.get("full_name")),
            "avatar": _text(pinner.get("image_small_url")),
            "url": f"{BASE}/{pinner.get('username')}/" if pinner.get("username") else "",
        },
    }


def profile(obj):
    """``UserResource`` -> the card ``.pinterest user`` draws."""
    username = _text(obj.get("username"))
    return {
        "username": username,
        "name": _text(obj.get("full_name")) or username,
        "about": _text(obj.get("about")),
        "avatar": _text(obj.get("image_xlarge_url") or obj.get("image_large_url")),
        "followers": _num(obj.get("follower_count")),
        "following": _num(obj.get("following_count")),
        "pins": _num(obj.get("pin_count")),
        "boards": _num(obj.get("board_count")),
        "website": _text(obj.get("website_url")),
        "url": f"{BASE}/{username}/" if username else BASE,
    }


def board(obj):
    """``BoardResource`` -> the line printed above a board's pins."""
    owner = obj.get("owner") or {}
    username = _text(owner.get("username"))
    slug = _text(obj.get("url")).strip("/").split("/")[-1]
    return {
        "name": _text(obj.get("name")),
        "about": _text(obj.get("description")),
        "cover": _text(obj.get("image_cover_url")),
        "pins": _num(obj.get("pin_count")),
        "followers": _num(obj.get("follower_count")),
        "owner": _text(owner.get("full_name")) or username,
        "url": _abs(obj.get("url")) or (f"{BASE}/{username}/{slug}/" if username else ""),
    }


def board_hit(obj):
    """One row of board search."""
    owner = obj.get("owner") or {}
    return {
        "name": _text(obj.get("name")),
        "pins": _num(obj.get("pin_count")),
        "followers": _num(obj.get("follower_count")),
        "owner": _text(owner.get("username")),
        "url": _abs(obj.get("url")),
    }


def user_hit(obj):
    """One row of people search."""
    username = _text(obj.get("username"))
    return {
        "username": username,
        "name": _text(obj.get("full_name")) or username,
        "followers": _num(obj.get("follower_count")),
        "pins": _num(obj.get("pin_count")),
        "boards": _num(obj.get("board_count")),
        "url": f"{BASE}/{username}/" if username else BASE,
    }
