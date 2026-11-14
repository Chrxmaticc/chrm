"""
Local stand-in for chrm-api's GET /api/engine/bots.

The real API needs a Neon DATABASE_URL. This mock serves the same JSON shape from
values in .env so the engine can be run and tested locally without a database.

Run:  .venv/bin/python mock_api.py
Then point the engine at it: API_URL=http://127.0.0.1:8080
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


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/api/engine/bots"):
            if self.headers.get("x-engine-secret") != ENGINE_SECRET:
                return self._json(401, {"detail": "Unauthorized"})
            return self._json(200, users())
        if self.path in ("/", "/health"):
            return self._json(200, {"status": "mock api is online"})
        return self._json(404, {"detail": "not found"})

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
