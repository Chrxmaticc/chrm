"""Extension discovery for the package layout.

A cog is a folder under ``plugins/`` that contains ``plugin.py``::

    plugins/
        automation/
            __init__.py     re-exports setup()
            plugin.py       <- this is what makes it a cog
            extended/       sub-cogs (mixins), never loaded on their own

``load_extension`` is given the package name (``plugins.config``), not
``plugins.config.plugin``, so ``.reload automation`` in ``plugins/general``
keeps working and the package's ``__init__`` stays the single entry point.

Framework cogs (``core/context.py``, ``core/client/helper.py``) are loaded explicitly by
``core/chrm.py`` and are deliberately *not* discovered here: they are part of the
framework, not of the plugin surface a user can reload.
"""
import os

PLUGINS_DIR = "plugins"

#: cogs that live in the framework rather than in plugins/
#:
#: ``core.client.helper`` is deliberately not loaded: it is a slash-command bot
#: (``app_commands``, ``discord.ui`` modals, ``Bot.tree``) and ``discord.py-self``
#: 2.x ships none of those -- a user account cannot register application commands.
#: Importing it therefore always raised ``ImportError: cannot import name
#: 'app_commands' from 'discord'`` and left a [PLUGIN ERROR] line on every boot.
FRAMEWORK_EXTENSIONS = ("core.context",)


def iter_extensions(root: str = PLUGINS_DIR):
    """Return the loadable extension names found under ``root``, sorted."""
    if not os.path.isdir(root):
        return []
    names = []
    for entry in sorted(os.listdir(root)):
        if entry.startswith((".", "_")):
            continue
        package = os.path.join(root, entry)
        if os.path.isdir(package) and os.path.isfile(os.path.join(package, "plugin.py")):
            names.append(f"{root}.{entry}")
    return names
