from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import requests


@dataclass(slots=True)
class LLMConfig:
    provider: str = "auto"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    ollama_api_key: str = ""
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash-lite"
    timeout_seconds: int = 90


class LLMClient:
    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self._provider = self._resolve_provider()

    @property
    def provider(self) -> str:
        return self._provider

    @property
    def available(self) -> bool:
        return self._provider in {"ollama", "gemini"}

    def _resolve_provider(self) -> str:
        preferred = (self.config.provider or "auto").strip().lower()
        if preferred == "gemini" and self.config.gemini_api_key:
            return "gemini"
        if preferred == "ollama" and self._ollama_available():
            return "ollama"
        if preferred == "none":
            return "none"
        if self.config.gemini_api_key:
            return "gemini"
        if self._ollama_available():
            return "ollama"
        return "none"

    def _ollama_available(self) -> bool:
        try:
            headers = self._ollama_headers()
            response = requests.get(
                f"{self.config.ollama_url.rstrip('/')}/api/tags",
                headers=headers,
                timeout=2.5,
            )
            return response.ok
        except requests.RequestException:
            return False

    def _ollama_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.config.ollama_api_key:
            headers["Authorization"] = f"Bearer {self.config.ollama_api_key}"
        return headers

    def chat(
        self,
        *,
        system: str,
        user: str,
        json_mode: bool = False,
        temperature: float = 0.1,
    ) -> str | None:
        if self._provider == "ollama":
            return self._ollama_chat(system=system, user=user, json_mode=json_mode, temperature=temperature)
        if self._provider == "gemini":
            return self._gemini_chat(system=system, user=user, json_mode=json_mode, temperature=temperature)
        return None

    def _ollama_chat(self, *, system: str, user: str, json_mode: bool, temperature: float) -> str | None:
        payload: dict[str, Any] = {
            "model": self.config.ollama_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": {"temperature": temperature},
        }
        if json_mode:
            payload["format"] = "json"
        try:
            response = requests.post(
                f"{self.config.ollama_url.rstrip('/')}/api/chat",
                headers=self._ollama_headers(),
                json=payload,
                timeout=self.config.timeout_seconds,
            )
            response.raise_for_status()
            return str(response.json().get("message", {}).get("content", "")).strip() or None
        except (requests.RequestException, ValueError):
            return None

    def _gemini_chat(self, *, system: str, user: str, json_mode: bool, temperature: float) -> str | None:
        endpoint = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.config.gemini_model}:generateContent"
        )
        payload: dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"temperature": temperature},
        }
        if json_mode:
            payload["generationConfig"]["responseMimeType"] = "application/json"
        try:
            response = requests.post(
                endpoint,
                params={"key": self.config.gemini_api_key},
                json=payload,
                timeout=self.config.timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
            parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
            text = "".join(str(part.get("text", "")) for part in parts).strip()
            return text or None
        except (requests.RequestException, ValueError, IndexError):
            return None


def config_from_mapping(values: dict[str, Any]) -> LLMConfig:
    def get(name: str, default: str = "") -> str:
        env = os.getenv(name)
        if env:
            return str(env).strip()
        return str(values.get(name, default) or default).strip()

    return LLMConfig(
        provider=get("AI_PROVIDER", "auto"),
        ollama_url=get("OLLAMA_URL", "http://localhost:11434"),
        ollama_model=get("OLLAMA_MODEL", "llama3.2"),
        ollama_api_key=get("OLLAMA_API_KEY", ""),
        gemini_api_key=get("GEMINI_API_KEY", ""),
        gemini_model=get("GEMINI_MODEL", "gemini-3.5-flash-lite"),
    )
