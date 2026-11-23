"""Trivia questions: ``(question, accepted answers, category)``.

Answers are matched case- and punctuation-insensitively, and any one of the
listed spellings is accepted -- so abbreviations do not need a second command.
"""

CATEGORIES = ("general", "games", "music", "movies", "history", "science")

QUESTIONS = [
    ("what is the largest planet in the solar system?", ["jupiter"], "science"),
    ("what gas do plants breathe in?", ["carbon dioxide", "co2"], "science"),
    ("how many bones are in the adult human body?", ["206"], "science"),
    ("what is the chemical symbol for gold?", ["au"], "science"),
    ("what force keeps planets in orbit?", ["gravity"], "science"),
    ("what is the hardest natural substance on earth?", ["diamond"], "science"),
    ("what part of the cell contains dna?", ["nucleus"], "science"),
    ("how many hearts does an octopus have?", ["3", "three"], "science"),
    ("what is the study of earthquakes called?", ["seismology"], "science"),
    ("what planet is known as the red planet?", ["mars"], "science"),

    ("what is the best-selling video game of all time?", ["minecraft"], "games"),
    ("which company made the playstation?", ["sony"], "games"),
    ("what is mario's brother called?", ["luigi"], "games"),
    ("in chess, which piece can only move diagonally?", ["bishop"], "games"),
    ("what game features a battle royale island called fortnite?", ["fortnite"], "games"),
    ("what is the highest rank in valorant?", ["radiant"], "games"),
    ("which pokemon is number 1 in the pokedex?", ["bulbasaur"], "games"),
    ("what console did nintendo release after the wii?", ["wii u"], "games"),
    ("what is the name of the blocky world in minecraft?", ["overworld"], "games"),
    ("how many players are on a soccer team on the field?", ["11", "eleven"], "games"),

    ("who sang \"shape of you\"?", ["ed sheeran"], "music"),
    ("which band wrote \"bohemian rhapsody\"?", ["queen"], "music"),
    ("what instrument has 88 keys?", ["piano"], "music"),
    ("who is known as the king of pop?", ["michael jackson"], "music"),
    ("what does \"fortissimo\" mean in music?", ["very loud", "loud"], "music"),
    ("which artist released the album \"1989\"?", ["taylor swift"], "music"),
    ("how many strings does a standard guitar have?", ["6", "six"], "music"),
    ("what genre is known for improvisation and swing?", ["jazz"], "music"),

    ("who directed \"jurassic park\"?", ["steven spielberg", "spielberg"], "movies"),
    ("what is the name of the wizard school in harry potter?", ["hogwarts"], "movies"),
    ("which movie features the line \"i'll be back\"?", ["terminator", "the terminator"], "movies"),
    ("who played iron man in the marvel movies?", ["robert downey jr", "robert downey junior", "rdj"], "movies"),
    ("what is the highest-grossing film of all time?", ["avatar"], "movies"),
    ("in toy story, what is the cowboy's name?", ["woody"], "movies"),
    ("what color is shrek?", ["green"], "movies"),

    ("in what year did world war ii end?", ["1945"], "history"),
    ("who was the first person on the moon?", ["neil armstrong", "armstrong"], "history"),
    ("which empire built the colosseum?", ["roman empire", "rome", "romans"], "history"),
    ("what wall fell in 1989?", ["berlin wall"], "history"),
    ("who was the first us president?", ["george washington", "washington"], "history"),
    ("which ancient civilization built the pyramids at giza?", ["egypt", "egyptians", "ancient egypt"], "history"),

    ("how many continents are there?", ["7", "seven"], "general"),
    ("what is the capital of japan?", ["tokyo"], "general"),
    ("how many sides does a hexagon have?", ["6", "six"], "general"),
    ("what is the largest ocean?", ["pacific", "pacific ocean"], "general"),
    ("what color do you get mixing blue and yellow?", ["green"], "general"),
    ("how many minutes are in a full day?", ["1440"], "general"),
    ("what is the tallest mountain above sea level?", ["everest", "mount everest"], "general"),
    ("what language has the most native speakers?", ["mandarin", "chinese", "mandarin chinese"], "general"),
]
