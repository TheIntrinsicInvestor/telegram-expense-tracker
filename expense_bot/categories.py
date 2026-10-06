"""The fixed category set and keyword lookup. User-learned words win over built-ins."""

import re

CATEGORIES = (
    "Eating Out",
    "Groceries",
    "Transport",
    "Shopping",
    "Entertainment",
    "Bills",
    "Housing",
    "Health",
    "Travel",
    "Subscriptions",
    "Gifts",
    "Other",
)

_KEYWORDS_BY_CATEGORY = {
    "Eating Out": "lunch dinner breakfast brunch coffee pret nandos deliveroo ubereats takeaway kfc mcdonalds "
    "starbucks costa greggs restaurant bar pub drinks",
    "Groceries": "groceries grocery tesco sainsburys aldi lidl waitrose asda coop ocado morrisons mands ms",
    "Transport": "tfl tube bus uber train petrol bolt taxi oyster fuel parking",
    "Shopping": "shopping amazon clothes zara uniqlo primark asos",
    "Entertainment": "cinema concert tickets games steam",
    "Bills": "bills electricity gas water phone internet broadband wifi",
    "Housing": "rent council mortgage deposit",
    "Health": "pharmacy boots doctor dentist gp prescription",
    "Travel": "flights flight hotel airbnb hostel airline holiday ryanair easyjet",
    "Subscriptions": "netflix spotify gym disney prime icloud youtube chatgpt subscription",
    "Gifts": "gift gifts present birthday",
}

BUILTIN_KEYWORDS: dict[str, str] = {
    word: category for category, words in _KEYWORDS_BY_CATEGORY.items() for word in words.split()
}

_EDGE_RE = re.compile(r"^[^0-9a-z]+|[^0-9a-z]+$")


def normalise_word(word: str) -> str:
    cleaned = word.lower().replace("'", "").replace("’", "").replace("&", "")
    return _EDGE_RE.sub("", cleaned)


def first_word(note: str) -> str | None:
    words = note.split()
    return normalise_word(words[0]) or None if words else None


def resolve(note: str, learned: dict[str, str]) -> str | None:
    for raw in note.split():
        word = normalise_word(raw)
        if word in learned:
            return learned[word]
        if word in BUILTIN_KEYWORDS:
            return BUILTIN_KEYWORDS[word]
    return None
