"""games: quick standalone games that are not part of the unlock ladder.

    slots            three reels, fake money
    blackjack / hit / stand   one hand per channel
    unscramble / usolve       scrambled word, one channel at a time
    nhie             never have i ever
    topic            conversation starter
    wordcount        characters, words, sentences, reading time
"""
from .plugin import GamesMixin  # noqa: F401

__all__ = ["GamesMixin"]
