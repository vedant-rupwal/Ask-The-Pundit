import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


NAVIGATION_PATTERNS = [
    r"\bcookie policy\b",
    r"\bprivacy policy\b",
    r"\bsubscribe\b",
    r"\bsign in\b",
    r"\badvertisement\b",
    r"\bshare this\b",
]


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def content_hash(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def normalize_text(text: str) -> str:
    text = text or ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean_text(text: str) -> str:
    text = normalize_text(text)
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            lines.append("")
            continue
        lower = stripped.lower()
        if any(re.search(pattern, lower) for pattern in NAVIGATION_PATTERNS):
            continue
        if len(stripped) < 3:
            continue
        lines.append(stripped)
    return normalize_text("\n".join(lines))


def is_probably_english(text: str) -> bool:
    letters = [char for char in text if char.isalpha()]
    if not letters:
        return False
    ascii_letters = [char for char in letters if "a" <= char.lower() <= "z"]
    return len(ascii_letters) / len(letters) >= 0.75


def is_quality_document(text: str, min_chars: int = 200) -> bool:
    cleaned = clean_text(text)
    if len(cleaned) < min_chars:
        return False
    if not is_probably_english(cleaned):
        return False
    words = re.findall(r"\b\w+\b", cleaned)
    unique_ratio = len(set(word.lower() for word in words)) / max(len(words), 1)
    return unique_ratio >= 0.18


def domain_from_url(url: str) -> str:
    return urlparse(url or "").netloc.lower()


def write_jsonl(path: str | Path, rows) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(path: str | Path):
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)
