import time


def progress_bar(done: int, total: int, width: int = 16) -> str:
    """Render a text progress bar like '██████░░░░ 45/120 (37%)'."""
    total = max(total, 0)
    done = min(max(done, 0), total) if total else 0
    filled = round(width * done / total) if total else 0
    pct = round(100 * done / total) if total else 0
    return f"{'█' * filled}{'░' * (width - filled)} {done}/{total} ({pct}%)"


class ThrottledEditor:
    """Edit a Discord message at most once per `interval` seconds.

    Discord rate-limits message edits; progress callbacks may fire per email,
    so intermediate updates are dropped when they come in too fast.
    Use force=True for the final state.
    """

    def __init__(self, message, interval: float = 3.0):
        self.message = message
        self.interval = interval
        self._last = 0.0

    async def update(self, content: str, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last < self.interval:
            return
        try:
            await self.message.edit(content=content)
            self._last = now
        except Exception:
            pass
