"""File-based replacement for direct Anthropic API calls (see ai_queue/SPEC.md).

The bot never calls Claude over the network anymore. Instead:
  1. enqueue() writes a request JSON to data/ai_queue/requests/.
  2. An external, separately-scheduled consumer (a Claude Code invocation running on
     the Pi under the owner's Claude Pro subscription - see ai_queue/CONSUMER_PROMPT.md
     and deploy/pieapple-ai-consumer.*) picks it up, does the actual work, and writes a
     matching response JSON to data/ai_queue/responses/.
  3. poll_and_dispatch() runs on a bot-side job_queue timer (every minute, see
     handlers/ai_consumer.py) and consumes any response that has arrived: it hands the
     original request + response to the handler registered for that request's "type",
     then archives both files under data/ai_queue/log/ so they're never reprocessed.

Both sides poll on the same 1-minute cadence, so a round trip normally completes within
a couple of minutes of the request being queued.
"""

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Awaitable, Callable

from config import AI_QUEUE_DIR

logger = logging.getLogger(__name__)

_ROOT = Path(AI_QUEUE_DIR)
REQUESTS_DIR = _ROOT / "requests"
RESPONSES_DIR = _ROOT / "responses"
LOG_DIR = _ROOT / "log"

ResponseHandler = Callable[[dict, dict], Awaitable[None]]


def _ensure_dirs() -> None:
    for directory in (REQUESTS_DIR, RESPONSES_DIR, LOG_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def enqueue(request_type: str, chat_id: int, payload: dict) -> str:
    """Writes a new request file and returns its id. Safe to call from the event loop -
    this is just a local file write, no network call."""
    _ensure_dirs()
    request_id = f"{int(time.time())}_{uuid.uuid4().hex[:8]}"
    request = {
        "id": request_id,
        "type": request_type,
        "chat_id": chat_id,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "payload": payload,
    }
    request_path = REQUESTS_DIR / f"{request_id}.json"
    request_path.write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Queued AI request %s (%s) at %s", request_id, request_type, request_path.resolve())
    return request_id


def _ready_ids() -> list[str]:
    """Response ids that have both a response file and its original request still on
    disk (the request is the only place chat_id/payload context lives)."""
    ids = []
    for response_path in RESPONSES_DIR.glob("*.json"):
        request_path = REQUESTS_DIR / response_path.name
        if request_path.exists():
            ids.append(response_path.stem)
        else:
            logger.warning("Response %s has no matching request - leaving it for now", response_path.name)
    return sorted(ids)


def _archive(request_id: str) -> None:
    _ensure_dirs()
    request_path = REQUESTS_DIR / f"{request_id}.json"
    response_path = RESPONSES_DIR / f"{request_id}.json"
    if request_path.exists():
        request_path.replace(LOG_DIR / f"{request_id}.request.json")
    if response_path.exists():
        response_path.replace(LOG_DIR / f"{request_id}.response.json")


async def poll_and_dispatch(handlers: dict[str, ResponseHandler]) -> None:
    """Consumes every response currently waiting. `handlers` maps a request "type" to
    an async callback(request: dict, response: dict). One bad/unhandled item is logged
    and archived rather than blocking the rest of the batch."""
    _ensure_dirs()
    for request_id in _ready_ids():
        request_path = REQUESTS_DIR / f"{request_id}.json"
        response_path = RESPONSES_DIR / f"{request_id}.json"
        try:
            request = json.loads(request_path.read_text(encoding="utf-8"))
            response = json.loads(response_path.read_text(encoding="utf-8"))
            handler = handlers.get(request["type"])
            if handler is None:
                logger.error("No handler registered for AI response type %r (id %s)", request["type"], request_id)
            else:
                await handler(request, response)
        except Exception:
            logger.exception("Failed to consume AI response %s", request_id)
        finally:
            _archive(request_id)
