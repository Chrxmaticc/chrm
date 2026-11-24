"""One JSON fetch helper for the keyless public APIs the lookups use.

The engine already shares one aiohttp session (:mod:`core.api`); this module is
the thin request layer on top of it -- a browser-ish User-Agent (crates.io and a
few others reject the default), ``Accept: application/json``, and ``(data,
error)`` returns so a dead API becomes one readable line instead of a traceback.

``error`` is always a short human sentence. Every caller puts it straight into a
message, so it must never be an exception object or a stack.
"""
from __future__ import annotations

import asyncio

from core import api

USER_AGENT = "chrm-selfbot (https://github.com/Chrxmaticc/chrm)"

#: merged into every request unless the caller overrides a key
HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json"}


async def fetch_json(url: str, *, headers=None, **params):
    """``(data, error)`` from a public JSON endpoint."""
    request_headers = dict(HEADERS)
    request_headers.update(headers or {})
    try:
        async with api.session().get(
            url, params=params or None, headers=request_headers
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
