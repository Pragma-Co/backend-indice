import json
from urllib.request import Request, urlopen

from django.conf import settings


def ask_ollama(
    system_prompt: str,
    user_message: str,
    *,
    temperature: float = 0.2,
    response_format: dict | None = None,
) -> str:
    body = {
        "model": settings.OLLAMA_MODEL,
        "stream": False,
        "options": {"temperature": temperature},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    }
    if response_format is not None:
        body["format"] = response_format

    request = Request(
        f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/chat",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=settings.OLLAMA_TIMEOUT) as response:
        payload = json.loads(response.read())

    if not isinstance(payload, dict):
        raise ValueError("Invalid Ollama response")
    message = payload.get("message")
    if not isinstance(message, dict):
        raise ValueError("Invalid Ollama response")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Invalid Ollama response")
    return content.strip()
