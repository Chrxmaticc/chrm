"""Hangman words by category."""

WORDS = {
    "animals": [
        "elephant", "giraffe", "penguin", "dolphin", "cheetah", "kangaroo",
        "octopus", "squirrel", "flamingo", "hedgehog", "alligator", "butterfly",
        "rhinoceros", "chameleon", "porcupine", "jellyfish",
    ],
    "countries": [
        "brazil", "canada", "japan", "morocco", "norway", "portugal", "sweden",
        "thailand", "argentina", "australia", "indonesia", "madagascar",
        "philippines", "switzerland", "netherlands", "south korea",
    ],
    "games": [
        "minecraft", "fortnite", "zelda", "pokemon", "tetris", "overwatch",
        "valheim", "stardew", "skyrim", "halo", "portal", "terraria",
        "hollow knight", "among us", "rocket league", "counter strike",
    ],
    "food": [
        "pizza", "sushi", "pancake", "spaghetti", "avocado", "chocolate",
        "blueberry", "lasagna", "cinnamon", "watermelon", "sandwich", "popcorn",
        "pineapple", "mushroom", "brownie", "lemonade",
    ],
    "tech": [
        "keyboard", "monitor", "router", "algorithm", "database", "firewall",
        "python", "javascript", "compiler", "terminal", "bandwidth", "protocol",
        "bluetooth", "satellite", "processor", "encryption",
    ],
}

CATEGORIES = tuple(WORDS)
