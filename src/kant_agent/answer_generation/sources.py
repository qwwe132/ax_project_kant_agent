import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SOURCES_PATH = ROOT / "data" / "sources.md"

# 표 한 줄: | 문서 ID | 제목 | [Notion](https://...) | ...
ROW_PATTERN = re.compile(r"^\| (\S+) \| (.+?) \| .*?\((https?://[^)]+)\)")


def load_sources() -> dict[str, dict]:
    """data/sources.md 표에서 문서 ID별 제목과 원본 링크를 읽는다."""
    sources = {}
    for line in SOURCES_PATH.read_text(encoding="utf-8").splitlines():
        match = ROW_PATTERN.match(line)
        if match:
            doc_id, title, url = match.groups()
            title = re.sub(r" \(\d+\)$", "", title)  # 제목 끝의 " (1)" 제거
            sources[doc_id] = {"title": title, "url": url}
    return sources


SOURCES = load_sources()