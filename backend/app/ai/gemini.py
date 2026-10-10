"""Google Gemini over its REST API."""

import httpx2

from app.ai.base import AIError, AIProvider

# Tests put a stand-in for Google here.
transport: httpx2.BaseTransport | None = None

BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiProvider(AIProvider):
    def __init__(self, api_key: str, model: str):
        self._key = api_key
        self.name = model

    def generate_json(self, system: str, user: str, schema: dict) -> str:
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json", "responseSchema": schema},
        }
        try:
            with httpx2.Client(timeout=45, transport=transport) as client:
                response = client.post(f"{BASE}/{self.name}:generateContent", headers={"x-goog-api-key": self._key}, json=body)
        except httpx2.HTTPError as exc:
            raise AIError(f"Could not reach the AI service ({type(exc).__name__}).") from exc
        if response.status_code in (429, 500, 502, 503, 504):
            raise AIError("The AI service is busy or over its limit. It will be tried again.")
        if response.status_code in (400, 401, 403, 404):
            # A wrong key or model will not fix itself; the message never includes the key.
            raise AIError(f"The AI service refused the request ({response.status_code}). Check the Gemini key and model name.", retry=False)
        if response.status_code != 200:
            raise AIError(f"The AI service answered with an error ({response.status_code}).")
        try:
            candidate = response.json()["candidates"][0]
            return candidate["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise AIError("The AI service gave no usable answer (it may have blocked the content).") from exc


def provider_from_settings() -> AIProvider | None:
    from app.core.config import get_settings

    settings = get_settings()
    return GeminiProvider(settings.gemini_api_key, settings.ai_model) if settings.gemini_api_key else None
