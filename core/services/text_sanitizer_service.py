import html
import re

SENSITIVE_PATTERNS = (
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    re.compile(r"\b\d{3}[.\s]?\d{3}[.\s]?\d{3}[-.\s]?\d{2}\b"),
    re.compile(r"\b\d{2}[.\s]?\d{3}[.\s]?\d{3}/?\d{4}[-.\s]?\d{2}\b"),
    re.compile(r"(?<!\d)(?:\+?55[\s.-]*)?\(?[1-9]\d\)?[\s.-]*9?\d{4}[\s.-]?\d{4}(?!\d)"),
    re.compile(r"\bBearer\s+\S+", re.IGNORECASE),
    re.compile(
        r"\b(?:password|senha|secret|token|api[_ -]?key|chave(?:\s+de)?\s+acesso)"
        r"\s*[:=]\s*[^\s,;]+",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16})\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
)
CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")
MARKUP_TAGS = re.compile(r"</?mark\s*>", re.IGNORECASE)


def sanitize_text(text: str) -> str:
    sanitized = html.unescape(MARKUP_TAGS.sub("", text))
    sanitized = CONTROL_CHARACTERS.sub(" ", sanitized)
    for pattern in SENSITIVE_PATTERNS:
        sanitized = pattern.sub("[REDACTED]", sanitized)
    return re.sub(r"\s+", " ", sanitized).strip()
