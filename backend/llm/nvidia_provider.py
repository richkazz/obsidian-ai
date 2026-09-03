"""NVIDIA NIM provider (build.nvidia.com / integrate.api.nvidia.com).

NVIDIA hosts a large, constantly-changing catalog of open-weight models
(DeepSeek, Kimi, Llama, GLM, gpt-oss, NVIDIA's own Nemotron family, etc.)
behind a single OpenAI Chat Completions-compatible endpoint:

    https://integrate.api.nvidia.com/v1/chat/completions
    https://integrate.api.nvidia.com/v1/models

Auth is a Bearer API key (prefix "nvapi-") generated at
https://build.nvidia.com/settings/api-keys, conventionally read from the
NVIDIA_API_KEY environment variable.
"""

import os
import httpx
from typing import Optional

from .openai_provider import OpenAIProvider

NVIDIA_DEFAULT_BASE_URL = "https://integrate.api.nvidia.com"
NVIDIA_ENV_KEY = "NVIDIA_API_KEY"
NVIDIA_DEFAULT_MODEL = "moonshotai/kimi-k3"

POPULAR_MODELS: list[dict] = [
    {"id": "nvidia/nemotron-3-ultra-550b-a55b", "name": "Nemotron 3 Ultra 550B-A55B (reasoning)"},
    {"id": "nvidia/nemotron-3-super-120b-a12b", "name": "Nemotron 3 Super 120B-A12B (reasoning)"},
    {"id": "nvidia/nemotron-3-nano-30b-a3b", "name": "Nemotron 3 Nano 30B-A3B (reasoning)"},
    {"id": "deepseek-ai/deepseek-v4-pro-0813", "name": "DeepSeek V4 Pro"},
    {"id": "moonshotai/kimi-k3", "name": "Kimi K3"},
    {"id": "openai/gpt-oss-20b", "name": "gpt-oss-20b (reasoning)"},
    {"id": "meta/llama-3.3-70b-instruct", "name": "Llama 3.3 70B Instruct"},
]

_KNOWN_CONTEXT_LENGTHS: dict[str, int] = {
    "nvidia/nemotron-3-super-120b-a12b": 131_072,
    "nvidia/nemotron-3-nano-30b-a3b": 131_072,
    "nvidia/llama-3.1-nemotron-ultra-253b-v1": 131_072,
    "nvidia/llama-3.3-nemotron-super-49b-v1.5": 131_072,
}


class NvidiaProvider(OpenAIProvider):
    """OpenAI-compatible provider for models served through build.nvidia.com."""

    CONFIG_KEYS = OpenAIProvider.CONFIG_KEYS + ("chat_template_kwargs", "reasoning_budget")

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_id: Optional[str] = None,
        config: Optional[dict] = None,
    ):
        api_key = api_key or os.environ.get(NVIDIA_ENV_KEY)
        super().__init__(
            api_key=api_key,
            base_url=base_url or NVIDIA_DEFAULT_BASE_URL,
            model_id=model_id or NVIDIA_DEFAULT_MODEL,
            config=config,
        )

    async def list_models(self) -> list[dict]:
        """NVIDIA serves its catalog at <base>/v1/models (not <base>/models
        like OpenAIProvider's default), so this is overridden."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url.rstrip('/')}/v1/models",
                    headers=self._headers(),
                )
                response.raise_for_status()
                data = response.json()
                models = data.get("data", [])
                if models:
                    return [{"id": m["id"], "name": m.get("id", "")} for m in models]
        except Exception:
            pass
        return list(POPULAR_MODELS)

    async def get_context_length(self) -> Optional[int]:
        """NVIDIA doesn't expose a live context-length endpoint (unlike LM
        Studio) — skip network calls and use the static table or None."""
        return _KNOWN_CONTEXT_LENGTHS.get(self.model_id)


# Alias for backward compatibility
NVIDIANIMProvider = NvidiaProvider
