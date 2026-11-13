import json
import re
from functools import cache

UNFINISHED_UNICODE_ESCAPE = re.compile(r"\\u[0-9a-fA-F]{0,3}$")


@cache
def _string_field_pattern(key: str) -> re.Pattern:
    return re.compile(rf'"{re.escape(key)}"\s*:\s*"((?:[^"\\]|\\.)*)("?)', re.DOTALL)


def _decode_json_string(raw: str) -> str | None:
    try:
        return json.loads(f'"{raw}"', strict=False)
    except ValueError:
        return None


def read_partial_string_field(text: str, key: str) -> tuple[str, bool] | None:
    match = _string_field_pattern(key).search(text)
    if match is None:
        return None
    raw, closing_quote = match.groups()
    value = _decode_json_string(raw)
    if value is None:
        value = _decode_json_string(UNFINISHED_UNICODE_ESCAPE.sub("", raw))
    if value is None:
        return None
    return value.encode("utf-8", "ignore").decode("utf-8"), bool(closing_quote)
