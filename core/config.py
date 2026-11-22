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
    """One bot instance's configuration: config.json overlaid by the dashboard.

    The dashboard stores one JSON blob per user (``users.settings``). That blob is
    the only thing the sync loop can hand us, so :meth:`apply_blob` defines the
    contract. Three shapes exist in the wild and all of them are accepted:

    canonical (what the dashboard writes now)::

        {"prefixes": ["."], "delays_enabled": true, "delay_min": 1.5,
         "delay_max": 4.5, "features": {"afk": {...}}, "rpc": {...}}

    whole-document (what the old mock server seeded)::

        {"settings": {...}, "emojis": {...}, "features": {...}}

    legacy flat (first dashboard version)::

        {"prefix": ".", "delays_enabled": true, "afk": {...},
         "autorespond": {...}, "autoreact": {...}}

    Keys named like a namespace are merged into that namespace; feature keys are
    hoisted into ``features``; everything else lands under ``settings``, which is
    what ``get_setting``/``get_prefixes`` read.
    """

    #: declared feature keys, so cog writes survive a restart through the blob
    FEATURE_KEYS = ("afk", "autorespond", "autoreact", "custom_status")
    #: blob keys that address a whole namespace instead of a single setting
    NAMESPACES = ("settings", "features", "emojis")

    def __init__(self, user_data=None, path: str = CONFIG_PATH):
        try:
            with open(path, "r") as f:
                self.data = json.load(f)
        except (OSError, ValueError) as exc:
            print(f"[CONFIG] {path} unreadable ({exc}); using class defaults")
            self.data = {}

        self.blob = None
        self.apply_user(user_data)

    # ------------------------------------------------------------ dashboard
    def apply_user(self, user_data) -> None:
        """Apply an ``/api/engine/bots`` record (or a bare blob)."""
        if not isinstance(user_data, dict) or not user_data:
            self._with_defaults()
            return

        # An engine record carries the blob under "settings" next to transport
        # fields; those must not leak into the config document.
        if "settings" in user_data and any(
            key in user_data for key in ("token", "discord_id", "is_active")
        ):
            blob = user_data.get("settings") or {}
        else:
            blob = user_data
        self.apply_blob(blob)

    def apply_blob(self, blob: dict) -> None:
        """Merge a dashboard settings blob into the config document."""
        if not isinstance(blob, dict):
            self._with_defaults()
            return

        self.blob = json.loads(json.dumps(blob))
        scoped = {}

        for key, value in blob.items():
            if key in self.NAMESPACES and isinstance(value, dict):
                target = self.data.setdefault(key, {})
                for inner_key, inner_value in value.items():
                    if isinstance(inner_value, dict) and isinstance(target.get(inner_key), dict):
                        target[inner_key].update(inner_value)
                    else:
                        target[inner_key] = inner_value
            elif key in self.FEATURE_KEYS:
                self.data.setdefault("features", {})[key] = value
            else:
                scoped[key] = value

        # "prefix": "!" -> "prefixes": ["!"] (first dashboard version)
        prefix = scoped.pop("prefix", None)
        if "prefixes" not in scoped and prefix:
            scoped["prefixes"] = prefix if isinstance(prefix, list) else [prefix]

        if scoped:
            self.data.setdefault("settings", {}).update(scoped)

        self._with_defaults()

    def update_from_dashboard(self, user_data: dict) -> bool:
        """Re-apply a user record. Returns True only when the blob changed."""
        if not isinstance(user_data, dict):
            return False
        if "settings" in user_data and any(
            key in user_data for key in ("token", "discord_id", "is_active")
        ):
            blob = user_data.get("settings") or {}
        else:
            blob = user_data
        if blob == self.blob:
            return False
        self.apply_blob(blob)
        return True

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

    def __repr__(self) -> str:
        return f"<Config prefixes={self.get_prefixes()} features={sorted(self.data.get('features', {}))}>"
