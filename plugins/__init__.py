"""Plugins, one folder per cog.

    plugins/<cog>/
        __init__.py      re-exports setup() so ``load_extension("plugins.<cog>")`` works
        plugin.py        the Cog: assembles the sub-cog mixins, owns shared state
        extended/        the smaller cogs this category is made of
            <sub>/
                __init__.py
                plugin.py    a mixin class with that sub-cog's commands/listeners
                helpers.py   its module-level constants and functions, if any

A sub-cog is never loaded on its own -- it only exists as part of its category cog,
which is what the loader in ``core/loader.py`` discovers.
"""
