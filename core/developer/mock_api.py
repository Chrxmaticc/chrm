"""
Local stand-in for chrm-api's GET /api/engine/bots.

The real API needs a Neon DATABASE_URL. This mock serves the same JSON shape from
values in .env so the engine can be run and tested locally without a database.

Run:  .venv/bin/python -m core.developer.mock_api
Then point the engine at it: API_URL=http://127.0.0.1:8080

The cog-side client for this API lives in ``core/api.py``.
"""
import os
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

ENGINE_SECRET = os.environ.get("ENGINE_SECRET", "fallback_secret_123")
USER_TOKEN = os.environ.get("MOCK_USER_TOKEN", "")
DISCORD_ID = os.environ.get("MOCK_DISCORD_ID", "000000000000000000")
PORT = int(os.environ.get("MOCK_PORT", "8080"))

# settings mirror what the dashboard writes; keys line up with config.json
def users():
    return list(_USERS.values())


def _seed_users():
    if not USER_TOKEN:
        return []
    return [{
        "discord_id": DISCORD_ID,
        "token": USER_TOKEN,
        "settings": {
            "settings": {"prefix": ".", "delays_enabled": True,
                         "delay_min": 1.5, "delay_max": 4.5},
            "emojis": {
                "success": "\u2705", "error": "\u274c", "loading": "\u231b",
                "tea": "\U0001f375", "image": "\U0001f5bc", "afk": "\U0001f4a4",
            },
            "features": {"afk": {"enabled": False, "message": "afk"}},
        },
        "is_active": True,
    }]


# Mutable copy so PATCH writes are visible to later GETs.
_USERS = {u["discord_id"]: u for u in _seed_users()}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/api/engine/bots"):
            if self.headers.get("x-engine-secret") != ENGINE_SECRET:
                return self._json(401, {"detail": "Unauthorized"})
            return self._json(200, users())
        if self.path.startswith("/api/user/"):
            uid = self.path.rsplit("/", 1)[-1].split("?")[0]
            user = _USERS.get(uid)
            if not user:
                return self._json(200, {"settings": {}, "is_active": False})
            return self._json(200, {"settings": user["settings"], "is_active": user["is_active"]})
        if self.path in ("/", "/health"):
            return self._json(200, {"status": "mock api is online"})
        return self._json(404, {"detail": "not found"})

    def do_PATCH(self):
        """Mirrors chrm-api's PATCH /api/user/{discord_id}: shallow update of the settings blob."""
        if not self.path.startswith("/api/user/"):
            return self._json(404, {"detail": "not found"})
        uid = self.path.rsplit("/", 1)[-1].split("?")[0]
        user = _USERS.get(uid)
        if not user:
            return self._json(404, {"detail": "User not found"})
        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return self._json(400, {"detail": "invalid json"})

        if payload.get("is_active") is not None:
            user["is_active"] = payload["is_active"]
        if payload.get("settings"):
            user["settings"].update(payload["settings"])
        print(f"[mock-api] PATCH /api/user/{uid} ok")
        return self._json(200, {"status": "success"})

    def _json(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print(f"[mock-api] {self.address_string()} {fmt % args}")


if __name__ == "__main__":
    print(f"mock chrm-api on :{PORT}  (users: {len(users())} active)")
    if not USER_TOKEN:
        print("  ! MOCK_USER_TOKEN is empty -> engine will poll but start no bots")
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
