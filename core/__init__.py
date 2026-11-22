"""Engine core: the framework the plugins are built on.

    core/chrm.py        the engine itself -- ChrmInstance, the sync loop, the runner
    core/config.py      config.json as classes: ``EMOJIS.DENY``, ``SETTINGS.DELAY_MIN``
    core/context.py     everything on ``commands.Context``: approve/deny/warn +
                        ``send_bot_help`` (the ``.help`` surface lives here too)
    core/api.py         one shared aiohttp session + dashboard writes (client side)
    core/client/        loader.py (extension discovery), helper.py (optional side-bot)
    core/developer/     mock_api.py -- local stand-in for chrm-api (server side)
    core/ui/            cv2.py -- Components V2 payloads and discord.builders links

Server vs client, since both look like "the API":

    core/developer/mock_api.py   listens on a port   (python -m core.developer.mock_api)
    core/api.py                  talks to a port     (save_feature, save_settings)

``main.py`` stays a thin runner; anything importable belongs in here.
"""

from core import api  # noqa: F401
from core import context  # noqa: F401  installs the ``commands.Context`` helpers

__all__ = ["api", "context"]
