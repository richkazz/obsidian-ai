"""NVIDIA NIM (Inference Microservices) Provider."""

import logging
import os
from typing import Optional

from .openai_provider import OpenAIProvider

logger = logging.getLogger(__name__)


class NVIDIANIMProvider(OpenAIProvider):
    """
    NVIDIA NIM (Inference Microservices) Provider.

    NVIDIA NIM exposes an OpenAI-compatible REST API for their model catalog.
    This provider extends OpenAIProvider to automatically route traffic to
    NVIDIA's integration endpoint and handle NVIDIA-specific authentication.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_id: str = "nvidia/nemotron-3-ultra-550b-a55b",
        config: Optional[dict] = None,
    ):
        resolved_api_key = api_key or os.environ.get("NVIDIA_API_KEY")
        if not resolved_api_key:
            raise ValueError(
                "NVIDIA_API_KEY is missing. Please pass 'api_key' directly "
                "or set the 'NVIDIA_API_KEY' environment variable."
            )

        resolved_base_url = base_url or "https://integrate.api.nvidia.com/v1"

        super().__init__(
            api_key=resolved_api_key,
            base_url=resolved_base_url,
            model_id=model_id,
            config=config or {},
        )

        logger.debug(f"Initialized NVIDIANIMProvider routing to {self.base_url} for model {self.model_id}")

    async def get_context_length(self) -> Optional[int]:
        """
        Overrides the LM Studio-specific check in the base class.
        NVIDIA's hosted /v1/models endpoint does not expose context length directly
        in a standard format, so we return None to rely on static defaults.
        """
        return None
