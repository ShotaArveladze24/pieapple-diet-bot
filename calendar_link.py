"""Builds 'Add to Google Calendar' links (calendar.google.com/render).
No Google API or OAuth involved — just the public prefilled-event URL."""

from datetime import datetime, timedelta
from urllib.parse import urlencode

from config import TIMEZONE

MEAL_TIMES = {
    "breakfast": (7, 0),
    "lunch": (12, 30),
    "dinner": (19, 0),
}
_MEAL_DURATION_MINUTES = 30


def build_event_link(
    title: str, event_date: str, time: tuple[int, int] | None, duration_minutes: int = 60
) -> str:
    """event_date is an ISO date (YYYY-MM-DD). time is (hour, minute) in TIMEZONE,
    or None for an all-day reminder."""
    if time is None:
        start = datetime.fromisoformat(event_date)
        end = start + timedelta(days=1)
        dates = f"{start.strftime('%Y%m%d')}/{end.strftime('%Y%m%d')}"
        params = {"action": "TEMPLATE", "text": title, "dates": dates}
    else:
        hour, minute = time
        start = datetime.fromisoformat(event_date).replace(hour=hour, minute=minute)
        end = start + timedelta(minutes=duration_minutes)
        dates = f"{start.strftime('%Y%m%dT%H%M%S')}/{end.strftime('%Y%m%dT%H%M%S')}"
        params = {"action": "TEMPLATE", "text": title, "dates": dates, "ctz": TIMEZONE}

    return "https://calendar.google.com/calendar/render?" + urlencode(params)


def build_meal_reminder_link(meal_type: str, meal_date: str, dish_name: str) -> str:
    """Prefilled link for a specific scheduled meal: dish name as title, at that
    meal type's usual time (07:00 breakfast, 12:30 lunch, 19:00 dinner)."""
    return build_event_link(dish_name, meal_date, MEAL_TIMES[meal_type], _MEAL_DURATION_MINUTES)
