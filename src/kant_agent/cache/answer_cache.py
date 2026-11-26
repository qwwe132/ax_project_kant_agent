"""Answer cache: keep the full search + answer result.

The key mixes the question with everything that changes the answer
(search config, collection, index version, search settings, answer model,
prompt version). If any of them changes, the key changes, so an old answer
is never reused. path=None keeps entries in memory only.
"""

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CACHE_PATH = ROOT / ".cache" / "answer_cache.json"


def normalize(question: str) -> str:
    """Treat spacing and ending marks as the same question."""
    text = re.sub(r"\s+", " ", question).strip()
    return text.rstrip("?.!？。 ").strip()


def make_key(question: str, config: str, settings: dict) -> str:
    """Locker number: same inputs always give the same key.

    settings holds everything that can change the answer:
    {"search": collection, index version, search parameters, models,
     "answer": answer model, prompt version}.
    """
    payload = json.dumps(
        [normalize(question), config, settings], ensure_ascii=False, sort_keys=True
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class AnswerCache:
    def __init__(self, path: Path | None = CACHE_PATH):
        """path=None keeps entries in memory only (cleared on restart)."""
        self.path = path
        if path is not None and path.exists():
            self.entries = json.loads(path.read_text(encoding="utf-8"))
        else:
            self.entries = {}

    def get(self, key: str):
        """Return the saved result, or None if this key was never saved."""
        entry = self.entries.get(key)
        return entry["value"] if entry else None

    def put(self, key: str, value: dict, info: dict) -> None:
        """Save one result. Errors are not saved."""
        if value.get("status") == "error":
            return
        self.entries[key] = {
            "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "info": info,
            "value": value,
        }
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.entries, ensure_ascii=False, indent=2), encoding="utf-8"
        )
