"""config.json, reachable as classes: ``EMOJIS.DENY``, ``SETTINGS.DELAY_MIN``.

Two layers, deliberately:

* the **defaults** below are class attributes, so any module can read one without
  a bot instance, a file handle or a lookup: ``from core.config import EMOJIS``
  then ``EMOJIS.DENY``. Keys match ``config.json -> emojis`` so the file and the
  class stay one vocabulary (``SUCCESS``, ``ERROR``, ``LOADING``, ``TEA``,
  ``IMAGE``, ``AFK``), with the feedback aliases ``APPROVE`` / ``DENY`` / ``WARN``
  that :mod:`core.context` uses.
* the **instance** is a :class:`Config` that loads ``config.json`` once and then
  overlays whatever the dashboard sends for that user. ``bot.config.data`` is still
  the mutable dict every cog writes into, and ``bot.config.get_emoji("error")``
  still resolves instance value -> class default -> empty string.

Before this module the defaults existed in three places at once: ``config.json``,
hardcoded fallbacks in ``main.py`` (``{"enabled": False, "message": "afk"}``), and
literal emoji in ``core/context.py``. Adding an emoji meant editing three files.
"""
import json

#: where the per-install defaults live
CONFIG_PATH = "config.json"

#: dashboard timestamps arrive in seconds or milliseconds
_MS_THRESHOLD = 1e11


class Emojis:
    """Keys of ``config.json -> emojis``, plus the feedback aliases."""

    SUCCESS = "\u2714\ufe0f"
    ERROR = "\U0001f6ab"
    LOADING = "\U0001f97d"
    TEA = "\U0001f9cb"
    IMAGE = "\U0001f3d9\ufe0f"
    AFK = "\U0001f642\u200d\u2195\ufe0f"

    # what core.context.approve/deny/warn fall back to
    APPROVE = SUCCESS
    DENY = ERROR
    WARN = "\u26a0\ufe0f"


class Settings:
    """Keys of ``config.json -> settings``."""

    PREFIXES = (".", ",", "?")
    DELAYS_ENABLED = True
    DELAY_MIN = 1.5
    DELAY_MAX = 4.5


class Features:
    """Keys of ``config.json -> features``."""

    AFK = {"enabled": False, "message": "afk"}
    AUTORESPOND = {}
    AUTOREACT = {}
    CUSTOM_STATUS = None


#: shorthands: ``from core.config import EMOJIS`` / ``SETTINGS`` / ``FEATURES``
EMOJIS = Emojis
SETTINGS = Settings
FEATURES = Features


class Config:
    """One bot instance's configuration: config.json overlaid by the dashboard."""

    def __init__(self, user_data=None, path: str = CONFIG_PATH):
        try:
            with open(path, "r") as f:
                self.data = json.load(f)
        except (OSError, ValueError) as exc:
            print(f"[CONFIG] {path} unreadable ({exc}); using class defaults")
            self.data = {}

        if user_data:
            self.data.update(user_data)

        self._with_defaults()

    # ------------------------------------------------------------ defaults
    def _with_defaults(self):
        """Fill in structure/keys every cog assumes exists."""
        settings = self.data.setdefault("settings", {})
        settings.setdefault("prefixes", list(SETTINGS.PREFIXES))
        settings.setdefault("delays_enabled", SETTINGS.DELAYS_ENABLED)
        settings.setdefault("delay_min", SETTINGS.DELAY_MIN)
        settings.setdefault("delay_max", SETTINGS.DELAY_MAX)

        features = self.data.setdefault("features", {})
        for key, default in (
            ("afk", FEATURES.AFK),
            ("autorespond", {}),
            ("autoreact", {}),
            ("custom_status", None),
        ):
            features.setdefault(key, dict(default) if isinstance(default, dict) else default)

    # ------------------------------------------------------------ lookups
    def get_emoji(self, name: str) -> str:
        """Instance override -> class default -> empty string."""
        value = self.data.get("emojis", {}).get(name)
        if value:
            return value
        return getattr(EMOJIS, name.upper(), "") or ""

    def get_setting(self, name: str, default=None):
        if name in self.data.get("settings", {}):
            return self.data["settings"][name]
        return getattr(SETTINGS, name.upper(), default)

    def get_prefixes(self) -> list:
        """Active prefixes, always including ``.`` so the account can never lock itself out."""
        prefixes = list(self.data.get("settings", {}).get("prefixes", SETTINGS.PREFIXES))
        if "." not in prefixes:
            prefixes.append(".")
        return prefixes

    def update_from_dashboard(self, user_data: dict) -> None:
        """Merge the settings blob the sync loop received (shallow, like the API)."""
        if user_data:
            self.data.update(user_data)
            self._with_defaults()

    def __repr__(self) -> str:
        return f"<Config prefixes={self.get_prefixes()} features={sorted(self.data.get('features', {}))}>"
