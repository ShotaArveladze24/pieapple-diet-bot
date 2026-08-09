"""Sincronizzazione pasti pianificati con Google Calendar."""

from datetime import datetime, timedelta

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from config import GOOGLE_CALENDAR_ID, GOOGLE_TOKEN_PATH, TIMEZONE

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]

_MEAL_TIMES = {
    "breakfast": (7, 0),
    "lunch": (12, 30),
    "dinner": (19, 0),
}
_MEAL_DURATION_MINUTES = 30


def _load_credentials() -> Credentials:
    creds = Credentials.from_authorized_user_file(GOOGLE_TOKEN_PATH, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(GOOGLE_TOKEN_PATH, "w", encoding="utf-8") as token_file:
            token_file.write(creds.to_json())
    return creds


def _get_service():
    return build("calendar", "v3", credentials=_load_credentials())


def _event_window(meal_date: str, meal_type: str) -> tuple[datetime, datetime]:
    hour, minute = _MEAL_TIMES[meal_type]
    start = datetime.fromisoformat(meal_date).replace(hour=hour, minute=minute)
    end = start + timedelta(minutes=_MEAL_DURATION_MINUTES)
    return start, end


def build_description(base_description: str, recipe_id: int | None, link: str | None) -> str:
    parts = []
    if base_description:
        parts.append(base_description)
    if recipe_id:
        parts.append(f"Recipe ID: {recipe_id}")
    if link:
        parts.append(link)
    return "\n".join(parts)


def create_event(
    meal_date: str,
    meal_type: str,
    dish_name: str,
    description: str,
    recipe_id: int | None = None,
    link: str | None = None,
) -> str:
    start, end = _event_window(meal_date, meal_type)
    event = {
        "summary": f"{meal_type.capitalize()}: {dish_name}",
        "description": build_description(description, recipe_id, link),
        "start": {"dateTime": start.isoformat(), "timeZone": TIMEZONE},
        "end": {"dateTime": end.isoformat(), "timeZone": TIMEZONE},
    }
    created = _get_service().events().insert(calendarId=GOOGLE_CALENDAR_ID, body=event).execute()
    return created["id"]


def update_event(
    event_id: str,
    dish_name: str,
    description: str,
    meal_type: str,
    recipe_id: int | None = None,
    link: str | None = None,
) -> None:
    service = _get_service()
    event = service.events().get(calendarId=GOOGLE_CALENDAR_ID, eventId=event_id).execute()
    event["summary"] = f"{meal_type.capitalize()}: {dish_name}"
    event["description"] = build_description(description, recipe_id, link)
    service.events().update(calendarId=GOOGLE_CALENDAR_ID, eventId=event_id, body=event).execute()


def delete_event(event_id: str) -> None:
    _get_service().events().delete(calendarId=GOOGLE_CALENDAR_ID, eventId=event_id).execute()
