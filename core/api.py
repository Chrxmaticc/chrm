"""One aiohttp session for the whole engine, plus the dashboard write helpers.

Before this module every cog opened its own ``async with aiohttp.ClientSession()``
(26 of them, 15 files). On a box that runs one bot instance per dashboard user and
kills itself at ~460MB RSS, that is a fresh TCP+TLS handshake per command and a
connection pool that is thrown away immediately.

So: one lazily-created session, shared by every cog, closed by ``core/chrm.py`` on
shutdown. Cogs never touch ``aiohttp`` for dashboard calls -- they call
:func:`save_feature`, :func:`save_settings` or :func:`patch_user`.

Note the split of duties in ``core/``:

* ``core/developer/mock_api.py`` -- the *server* side: a local stand-in for chrm-api
* ``core/api.py``            -- the *client* side: this module, what cogs call

Writes go to ``api_base.BASE_API``. Never hardcode the host here or in a cog:
``groups.py`` and ``delay.py`` used to read ``os.environ["BASE_API_URL"]`` directly,
so setting only ``API_URL`` sent their writes to a different host than everyone
else's, silently.
"""
from typing import Any, Optional

import aiohttp

from api_base import BASE_API

DEFAULT_TIMEOUT = 10

_session: Optional[aiohttp.ClientSession] = None


def session() -> aiohttp.ClientSession:
    """The shared session, created on first use and re-created after a close.

    There is no ``await`` between the check and the assignment, so on a single
    event loop this cannot race into two live sessions.
    """
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT))
    return _session


async def close() -> None:
    """Close the shared session. Safe to call twice, and from ``finally`` blocks."""
    global _session
    if _session is not None and not _session.closed:
        await _session.close()
    _session = None


async def request(method: str, path: str, *, tag: str = "API", **kwargs: Any):
    """Send a request to the dashboard and return the decoded body (or ``None``).

    Network and JSON errors are logged against ``tag`` and swallowed: a failing
    dashboard must not take a command down with it.
    """
    url = f"{BASE_API}{path}"
    try:
        async with session().request(method, url, **kwargs) as resp:
            if resp.status >= 400:
                print(f"[{tag}] {method} {path} -> {resp.status}")
                return None
            if not resp.content_type or "json" not in resp.content_type:
                return None
            return await resp.json()
    except Exception as exc:  # noqa: BLE001 - never let the dashboard break a command
        print(f"[{tag}] {method} {path} failed: {type(exc).__name__}: {exc}")
        return None


async def patch_user(user_id: int, payload: dict, *, tag: str = "API") -> bool:
    """``PATCH /api/user/<id>`` -- the dashboard's shallow settings update."""
    result = await request("PATCH", f"/api/user/{user_id}", json=payload, tag=tag)
    return result is not None


async def get_user(user_id: int, *, tag: str = "API") -> Optional[dict]:
    """``GET /api/user/<id>`` -- current settings blob for one user."""
    return await request("GET", f"/api/user/{user_id}", tag=tag)


async def save_feature(bot, feature_key: str, data: Any, *, tag: str = "API") -> bool:
    """Store ``data`` under ``features[feature_key]`` locally, then persist it.

    This is the one copy of what used to be pasted into profile, scheduled, gc and
    automation -- four implementations that had drifted apart.
    """
    if "features" not in bot.config.data:
        bot.config.data["features"] = {}
    bot.config.data["features"][feature_key] = data
    return await patch_user(
        bot.user_id,
        {"settings": {"features": bot.config.data["features"]}},
        tag=tag,
    )


async def save_settings(bot, **settings: Any) -> bool:
    """Update ``bot.config.data["settings"]`` with the given keys and persist them."""
    if "settings" not in bot.config.data:
        bot.config.data["settings"] = {}
    bot.config.data["settings"].update(settings)
    return await patch_user(bot.user_id, {"settings": settings}, tag="SETTINGS")
