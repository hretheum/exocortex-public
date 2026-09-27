"""Cheap detection of Polish text in code comments and strings."""

from __future__ import annotations

import re

DIACRITICS = re.compile(r"[ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]")
STOPWORDS = {
    "i", "w", "z", "na", "do", "nie", "się", "sie", "jest", "że", "ze", "to", "dla", "jak", "oraz", "ale",
    "po", "przy", "bez", "gdy", "już", "juz", "tylko", "może", "moze", "być", "byc", "są", "sa", "czy",
    "od", "też", "tez", "tego", "który", "ktory", "która", "ktora", "które", "ktore", "jeśli", "jesli",
    "więc", "wiec", "żeby", "zeby", "teraz", "tutaj", "zawsze", "nigdy", "albo", "lub", "tak", "jako",
    "gdzie", "kiedy", "przez", "przed", "potem", "wtedy", "bo", "ten", "ta", "te", "tym", "tej", "tu",
    "wszystko", "trzeba", "zamiast", "czyli", "dopiero", "jeszcze", "bardzo", "także", "takze", "działa",
    "dziala", "brak", "gdyby", "nawet", "każdy", "kazdy", "sprawdza", "zwraca", "uwaga",
}
# Polish function words that are also everyday English words; they never count as evidence.
ENGLISH_TOO = {"to", "do", "i"}
WORD = re.compile(r"[A-Za-ząćęłńóśźżĄĆĘŁŃÓŚŹŻ]+")


NAMES = ("Eryk Orłowski", "Orłowski")  # proper names that carry diacritics in English text


def is_polish(text: str) -> bool:
    """True when the text is probably Polish: diacritics, or two or more Polish function words."""
    for name in NAMES:
        text = text.replace(name, "")
    if DIACRITICS.search(text):
        return True
    words = [w.lower() for w in WORD.findall(text)]
    if len(words) < 3:
        return False
    hits = sum(w in STOPWORDS and w not in ENGLISH_TOO for w in words)
    # "i", "w", "z", "to", "do", "na" alone also occur in English identifiers
    strong = sum(w in STOPWORDS and len(w) > 2 for w in words)
    return hits >= 3 or strong >= 2
