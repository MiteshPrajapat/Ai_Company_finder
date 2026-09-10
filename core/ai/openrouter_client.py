"""
Client for OpenRouter LLM API endpoints.
Provides completions, structured outputs, and connection health checking.
"""

import json
import httpx
from typing import Dict, Any, Optional, List
from config.settings import settings
from utils.logger import get_logger

logger = get_logger("openrouter_client")

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# Curated list of popular & effective models on OpenRouter
POPULAR_MODELS = [
    ("google/gemini-2.0-flash-exp:free", "Google Gemini 2.0 Flash (Free)"),
    ("meta-llama/llama-3.3-70b-instruct:free", "Llama 3.3 70B Instruct (Free)"),
    ("deepseek/deepseek-chat", "DeepSeek V3 (Fast & Low Cost)"),
    ("deepseek/deepseek-r1", "DeepSeek R1 (Reasoning)"),
    ("openai/gpt-4o-mini", "OpenAI GPT-4o Mini"),
    ("anthropic/claude-3.5-sonnet", "Anthropic Claude 3.5 Sonnet"),
    ("mistralai/mistral-large-2407", "Mistral Large 2"),
    ("qwen/qwen-2.5-72b-instruct", "Qwen 2.5 72B Instruct"),
]


class OpenRouterClient:
    """Handles communication with OpenRouter API."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        cfg = settings.get_config()
        self.api_key = (api_key or cfg.openrouter_api_key or "").strip()
        self.model = (model or cfg.openrouter_model or "google/gemini-2.0-flash-exp:free").strip()
        self.timeout = cfg.request_timeout

    def is_configured(self) -> bool:
        """Returns True if an API key is present."""
        return bool(self.api_key)

    def test_connection(self, api_key: Optional[str] = None) -> Dict[str, Any]:
        """
        Sends a minimal ping request to verify the API key is valid.
        """
        key = (api_key or self.api_key).strip()
        if not key:
            return {"success": False, "error": "OpenRouter API Key is empty."}

        headers = {
            "Authorization": f"Bearer {key}",
            "HTTP-Referer": "https://jobfinder.ai",
            "X-Title": "Job Finder AI",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "google/gemini-2.0-flash-exp:free",
            "messages": [
                {"role": "user", "content": "Respond with 'OK' only."}
            ],
            "max_tokens": 10
        }

        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(OPENROUTER_API_URL, headers=headers, json=payload)
                if resp.status_code == 200:
                    return {"success": True, "message": "API Key is valid and connected to OpenRouter."}
                elif resp.status_code == 401:
                    return {"success": False, "error": "Invalid API Key (HTTP 401 Unauthorized)."}
                elif resp.status_code == 402:
                    return {"success": False, "error": "Insufficient OpenRouter account credits (HTTP 402)."}
                else:
                    err_msg = resp.text[:200]
                    return {"success": False, "error": f"OpenRouter responded with HTTP {resp.status_code}: {err_msg}"}
        except httpx.ConnectTimeout:
            return {"success": False, "error": "Connection timed out reaching OpenRouter."}
        except Exception as e:
            return {"success": False, "error": f"Network error: {str(e)}"}

    def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 2000,
        response_format_json: bool = False
    ) -> Dict[str, Any]:
        """
        Sends a completion request to OpenRouter.
        """
        if not self.api_key:
            return {
                "success": False,
                "error": "OpenRouter API Key is not configured. Please add your key in Settings."
            }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://jobfinder.ai",
            "X-Title": "Job Finder AI",
            "Content-Type": "application/json"
        }

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        target_model = (model or self.model).strip()
        payload: Dict[str, Any] = {
            "model": target_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        if response_format_json:
            payload["response_format"] = {"type": "json_object"}

        try:
            logger.info(f"Sending request to OpenRouter with model {target_model}...")
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(OPENROUTER_API_URL, headers=headers, json=payload)

            if resp.status_code != 200:
                error_body = resp.text
                logger.error(f"OpenRouter error {resp.status_code}: {error_body}")
                return {
                    "success": False,
                    "error": f"API Error (HTTP {resp.status_code}): {error_body[:300]}"
                }

            data = resp.json()
            choices = data.get("choices", [])
            if not choices:
                return {"success": False, "error": "No response choices returned by OpenRouter."}

            content = choices[0].get("message", {}).get("content", "").strip()
            return {
                "success": True,
                "content": content,
                "model": target_model,
                "usage": data.get("usage", {})
            }

        except httpx.TimeoutException:
            logger.error("OpenRouter request timed out.")
            return {"success": False, "error": "Request timed out while waiting for AI response."}
        except Exception as e:
            logger.error(f"OpenRouter request failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
