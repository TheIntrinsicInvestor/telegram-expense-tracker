from expense_bot.categories import BUILTIN_KEYWORDS, CATEGORIES, first_word, normalise_word, resolve


def test_category_order():
    assert CATEGORIES[0] == "Eating Out" and CATEGORIES[-1] == "Other" and len(CATEGORIES) == 12


def test_builtin_values_are_categories():
    assert set(BUILTIN_KEYWORDS.values()) <= set(CATEGORIES)


def test_resolve_builtin():
    assert resolve("lunch", {}) == "Eating Out"


def test_resolve_case_and_apostrophe():
    assert resolve("Sainsbury's shop", {}) == "Groceries"


def test_resolve_second_word():
    assert resolve("big tesco run", {}) == "Groceries"


def test_learned_overrides_builtin():
    assert resolve("coffee", {"coffee": "Groceries"}) == "Groceries"


def test_learned_beats_later_builtin_word():
    assert resolve("zzz lunch", {"zzz": "Gifts"}) == "Gifts"


def test_unknown():
    assert resolve("xyzzy", {}) is None


def test_empty_note():
    assert resolve("", {}) is None and first_word("") is None


def test_first_word():
    assert first_word("Coffee pret") == "coffee"


def test_ampersand():
    assert normalise_word("M&S") == "ms"
    assert resolve("M&S", {}) == "Groceries"
