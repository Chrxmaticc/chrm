"""``lyrics_sync`` -- DISABLED, and not part of the Spoofing cog.

This sub-cog rewrote a Spotify presence line by line with the current lyric. It
has never loaded: it imports ``fetch_lyrics``/``parse_lines`` from the lyrics
sub-cog and ``run_lyric_presence`` from the spotify sub-cog, and none of those
three names exist anywhere in the tree. ``plugins/spoofing/plugin.py``
deliberately does not mix it in, so the engine does not print a load error for it
any more.

Kept here because the reverse-engineered presence trick in it (reuse the real
start/end pair so the progress bar keeps the true playback position) is worth
something. To revive it: implement ``fetch_lyrics``/``parse_lines`` in
``plugins/lookup/extended/lyrics/plugin.py``, add ``run_lyric_presence`` to
``plugins/spoofing/extended/spotify``, then add ``SpotifyLyricsMixin`` to the
``Spoofing`` class bases and rename its ``on_presence_update``.
"""
