"""Risoluzione delle etichette giorno (multilingua) in date ISO."""

import unicodedata
from datetime import date, datetime, timedelta

_WEEKDAY_NAMES = {
    "lunedi": 0, "monday": 0, "lunes": 0,
    "martedi": 1, "tuesday": 1, "martes": 1,
    "mercoledi": 2, "wednesday": 2, "miercoles": 2,
    "giovedi": 3, "thursday": 3, "jueves": 3,
    "venerdi": 4, "friday": 4, "viernes": 4,
    "sabato": 5, "saturday": 5, "sabado": 5,
    "domenica": 6, "sunday": 6, "domingo": 6,
}


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower().strip())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _weekday_from_label(day_label: str) -> int | None:
    normalized = _normalize(day_label)
    for name, index in _WEEKDAY_NAMES.items():
        if name in normalized:
            return index
    return None


_RELATIVE_DAY_WORDS = {
    "oggi": 0, "today": 0, "hoy": 0,
    "domani": 1, "tomorrow": 1, "manana": 1,
}


def parse_user_date(text: str) -> str | None:
    """Interpreta una data scritta liberamente dall'utente (oggi/domani/nome giorno/data
    esplicita) e restituisce una data ISO, oppure None se non riconosciuta."""
    normalized = _normalize(text)

    for word, offset in _RELATIVE_DAY_WORDS.items():
        if word in normalized:
            return (date.today() + timedelta(days=offset)).isoformat()

    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text.strip(), fmt).date().isoformat()
        except ValueError:
            continue

    weekday = _weekday_from_label(text)
    if weekday is not None:
        today = date.today()
        days_ahead = (weekday - today.weekday()) % 7
        return (today + timedelta(days=days_ahead)).isoformat()

    return None


def next_monday(reference: date | None = None) -> str:
    """Prossimo lunedi (oggi stesso se oggi e' gia' lunedi)."""
    today = reference or date.today()
    days_until_monday = (7 - today.weekday()) % 7
    return (today + timedelta(days=days_until_monday)).isoformat()


def monday_of_week(iso_date: str) -> str:
    d = date.fromisoformat(iso_date)
    return (d - timedelta(days=d.weekday())).isoformat()


_NEXT_WEEK_WORDS = ("prossima", "next", "proxima")
_THIS_WEEK_WORDS = ("questa", "this", "corrente", "current", "esta")


def parse_week_start(text: str) -> str | None:
    """Interpreta 'prossima settimana'/'questa settimana'/una data o giorno, e restituisce
    il lunedi di quella settimana in formato ISO, oppure None se non riconosciuto."""
    normalized = _normalize(text)

    if any(word in normalized for word in _NEXT_WEEK_WORDS):
        return next_monday()
    if any(word in normalized for word in _THIS_WEEK_WORDS):
        return monday_of_week(date.today().isoformat())

    explicit = parse_user_date(text)
    if explicit:
        return monday_of_week(explicit)

    return None


def resolve_day_date(day_label: str, fallback_index: int, week_monday: str) -> str:
    """Converte un'etichetta giorno (es. 'Lunedi', 'Lunes', 'Monday', o una data esplicita)
    in una data ISO, usando week_monday come inizio settimana per i nomi dei giorni."""
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(day_label.strip(), fmt).date().isoformat()
        except ValueError:
            continue

    weekday = _weekday_from_label(day_label)
    monday = date.fromisoformat(week_monday)
    if weekday is not None:
        return (monday + timedelta(days=weekday)).isoformat()
    return (monday + timedelta(days=fallback_index)).isoformat()
