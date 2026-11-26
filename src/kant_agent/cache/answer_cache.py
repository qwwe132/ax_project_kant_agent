"""Answer cache: keep the full search + answer result in a JSON file.

The key mixes the question with everything that changes the answer
(search config, index version, answer model, prompt version).
If any of them changes, the key changes, so an old answer is never reused.
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


def make_key(question: str, config: str, index_version: str,
             model: str, prompt_version: str) -> str:
    """Locker number: same inputs always give the same key."""
    parts = [normalize(question), config, index_version, model, prompt_version]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


class AnswerCache:
    def __init__(self, path: Path = CACHE_PATH):
        self.path = path
        if path.exists():
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
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.entries, ensure_ascii=False, indent=2), encoding="utf-8")