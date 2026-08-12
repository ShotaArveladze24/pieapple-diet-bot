"""Shared helpers for building Telegram-safe message text."""

TELEGRAM_MESSAGE_LIMIT = 4096


def chunk_message(text: str, limit: int = TELEGRAM_MESSAGE_LIMIT) -> list[str]:
    chunks: list[str] = []
    current = ""

    for line in text.split("\n"):
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit:
            if current:
                chunks.append(current)
                current = ""
            while len(line) > limit:
                chunks.append(line[:limit])
                line = line[limit:]
            current = line
        else:
            current = candidate

    if current:
        chunks.append(current)

    return chunks
