"""Surya OpenAI互換HTTP transport。"""

from __future__ import annotations

import base64
import io
import json
import urllib.request
from typing import Any

from PIL import Image


class SuryaTransport:
    def __init__(self, base_url: str, model: str, timeout_sec: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_sec = timeout_sec

    def recognize(
        self,
        image: Image.Image,
        *,
        prompt: str,
        max_tokens: int,
    ) -> str:
        payload = self._payload(image, prompt=prompt, max_tokens=max_tokens)
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_sec) as response:
            data: dict[str, Any] = json.loads(response.read().decode("utf-8"))
        return self._content(data)

    def _payload(
        self,
        image: Image.Image,
        *,
        prompt: str,
        max_tokens: int,
    ) -> dict[str, Any]:
        image_bytes = io.BytesIO()
        image.convert("RGB").save(image_bytes, format="PNG")
        encoded = base64.b64encode(image_bytes.getvalue()).decode("ascii")
        return {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{encoded}"},
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
            "temperature": 0,
            "top_p": 0.1,
            "seed": 0,
            "max_tokens": max_tokens,
        }

    @staticmethod
    def _content(data: dict[str, Any]) -> str:
        content = data["choices"][0]["message"]["content"]
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
        raise ValueError("Surya response content is not text")
