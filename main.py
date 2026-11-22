"""Entry point. The engine itself lives in ``core/chrm.py``.

    python main.py                      # start the engine (reads .env)
    python -m core.developer.mock_api   # local stand-in for the dashboard API
"""
import asyncio

from dotenv import load_dotenv

# Load .env before anything reads os.environ (PORT, API_URL, ENGINE_SECRET).
load_dotenv()

from core import chrm  # noqa: E402  -- must come after load_dotenv()


def run():
    asyncio.run(chrm.main())


if __name__ == "__main__":
    run()
