"""Single source of truth for the dashboard API base URL.

Two different things talk to the dashboard API:

  * the engine's sync loop  -> GET  <base>/api/engine/bots   (main.py)
  * commands/plugins        -> PATCH <base>/api/user/<id>     (this module)

Both must resolve to the same host, otherwise writes silently go somewhere else
(that is why commands were hitting the deployed API while the loop polled the mock).

Resolution order:
  BASE_API_URL  - explicit override for write calls
  API_URL       - reused, with the /api/engine/bots path stripped
  default       - the deployed API
"""
import os

from dotenv import load_dotenv

load_dotenv()

_ENGINE_PATH = "/api/engine/bots"
_DEFAULT_BASE = "https://chrm-api.onrender.com"


def _resolve_base():
    base = os.environ.get("BASE_API_URL") or os.environ.get("API_URL") or _DEFAULT_BASE
    base = base.strip().rstrip("/")
    if base.endswith(_ENGINE_PATH):
        base = base[: -len(_ENGINE_PATH)]
    return base


BASE_API = _resolve_base()
