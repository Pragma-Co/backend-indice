import json
from collections.abc import Iterator
from urllib.request import Request, urlopen

from django.conf import settings


def _chat_request(
    system_prompt: str,
    user_message: str,
    temperature: float,
    response_format: dict | None,
    stream: bool,
) -> Request:
    body = {
        "model": settings.OLLAMA_MODEL,
        "stream": stream,
        "options": {"temperature": temperature},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    }
    if response_format is not None:
        body["format"] = response_format

    return Request(
        f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/chat",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )


def _message_content(payload) -> str:
    if not isinstance(payload, dict) or "error" in payload:
        raise ValueError("Invalid Ollama response")
    message = payload.get("message")
    if not isinstance(message, dict):
        raise ValueError("Invalid Ollama response")
    content = message.get("content")
    if not isinstance(content, str):
        raise ValueError("Invalid Ollama response")
    return content


def ask_ollama(
    system_prompt: str,
    user_message: str,
    *,
    temperature: float = 0.2,
    response_format: dict | None = None,
) -> str:
    request = _chat_request(system_prompt, user_message, temperature, response_format, False)
    with urlopen(request, timeout=settings.OLLAMA_TIMEOUT) as response:
        payload = json.loads(response.read())

    content = _message_content(payload)
    if not content.strip():
        raise ValueError("Invalid Ollama response")
    return content.strip()


def stream_ollama(
    system_prompt: str,
    user_message: str,
    *,
    temperature: float = 0.2,
    response_format: dict | None = None,
) -> Iterator[str]:
    request = _chat_request(system_prompt, user_message, temperature, response_format, True)
    with urlopen(request, timeout=settings.OLLAMA_TIMEOUT) as response:
        for line in response:
            if not line.strip():
                continue
            payload = json.loads(line)
            content = _message_content(payload)
            if content:
                yield content
            if payload.get("done"):
                return
