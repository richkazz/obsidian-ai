"""Factory for creating MAF ChatAgent and ChatClient instances."""

import inspect
import json
import logging
from typing import Any, Optional
from fastapi import HTTPException

from agent_framework import Agent
from agent_framework.openai import OpenAIChatClient
from agent_framework.anthropic import AnthropicClient
from agent_framework.gemini import GeminiChatClient
from agent_framework.foundry import FoundryChatClient

from .nvidia_provider import NvidiaProvider

logger = logging.getLogger(__name__)


class ChatAgent(Agent):
    """MAF ChatAgent subclass extending Agent with MAF client integration and options propagation."""

    def __init__(
        self,
        client: Any,
        instructions: Optional[str] = None,
        tools: Any = None,
        default_options: Optional[dict] = None,
        **kwargs,
    ):
        opts = dict(default_options or {})
        if instructions is not None:
            opts["instructions"] = instructions
        super().__init__(
            client=client,
            instructions=instructions,
            tools=tools,
            default_options=opts,
            **kwargs,
        )

    @property
    def instructions(self) -> Optional[str]:
        if self.default_options and isinstance(self.default_options, dict):
            return self.default_options.get("instructions")
        return None

    async def chat(self, *args, **kwargs):
        """Backwards compatibility delegation for legacy code calling provider.chat."""
        if hasattr(self.client, "chat") and callable(self.client.chat):
            return await self.client.chat(*args, **kwargs)
        raise NotImplementedError("Chat completion delegate not supported on underlying client")

    async def chat_stream(self, *args, **kwargs):
        """Backwards compatibility delegation for legacy code calling provider.chat_stream."""
        if hasattr(self.client, "chat_stream") and callable(self.client.chat_stream):
            stream = self.client.chat_stream(*args, **kwargs)
            if inspect.isawaitable(stream):
                stream = await stream
            async for chunk in stream:
                yield chunk
            return
        raise NotImplementedError("Streaming delegate not supported on underlying client")

    async def list_models(self) -> list[dict]:
        """List models delegate."""
        if hasattr(self.client, "list_models") and callable(self.client.list_models):
            return await self.client.list_models()
        return []

    async def test_connection(self) -> bool:
        """Test connection delegate."""
        if hasattr(self.client, "test_connection") and callable(self.client.test_connection):
            return await self.client.test_connection()
        return True


def create_provider_from_config(
    provider_type: str,
    api_key: Optional[str],
    base_url: Optional[str],
    model_id: str,
    config: Optional[dict] = None,
    system_prompt: Optional[str] = None,
    default_options: Optional[dict] = None,
) -> ChatAgent:
    """Create a MAF ChatAgent instance configured with a MAF-supported ChatClient."""
    config = config or {}
    options = dict(default_options or {})

    # Extract options from config if provided
    if "temperature" in config and "temperature" not in options:
        options["temperature"] = config["temperature"]
    if "max_tokens" in config and "max_tokens" not in options:
        options["max_tokens"] = config["max_tokens"]

    known_providers = {
        "openai",
        "openrouter",
        "custom",
        "anthropic",
        "google",
        "gemini",
        "nvidia",
        "nvidia_nim",
        "foundry",
    }

    if provider_type not in known_providers:
        raise ValueError(f"Unknown provider type: {provider_type}")

    try:
        if provider_type in ("openai", "openrouter", "custom"):
            url = base_url
            if provider_type == "openrouter":
                url = base_url or "https://openrouter.ai/api/v1"
            client = OpenAIChatClient(
                model=model_id,
                api_key=api_key,
                base_url=url,
            )
            client.api_key = api_key

        elif provider_type == "anthropic":
            client = AnthropicClient(
                model=model_id,
                api_key=api_key,
                base_url=base_url,
            )
            client.api_key = api_key

        elif provider_type in ("google", "gemini"):
            client = GeminiChatClient(
                model=model_id,
                api_key=api_key,
            )
            client.api_key = api_key

        elif provider_type in ("nvidia", "nvidia_nim"):
            client = NvidiaProvider(
                model_id=model_id,
                api_key=api_key,
                base_url=base_url,
                config=config,
            )
            client.api_key = api_key

        elif provider_type == "foundry":
            client = FoundryChatClient(
                model=model_id,
                api_key=api_key,
                base_url=base_url,
            )
            client.api_key = api_key

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to initialize client for provider {provider_type}: {e}")
        err_msg = str(e).lower()
        if any(term in err_msg for term in ("auth", "credential", "api_key", "unauthorized", "permission", "invalid key", "secret")):
            raise HTTPException(status_code=400, detail="Invalid provider credentials")
        raise HTTPException(status_code=500, detail=f"Provider initialization failed: {e}")

    agent = ChatAgent(
        client=client,
        instructions=system_prompt,
        default_options=options,
    )
    return agent


def create_provider(
    provider_record,
    system_prompt: Optional[str] = None,
    default_options: Optional[dict] = None,
) -> ChatAgent:
    """Create a MAF ChatAgent instance from a database record, decrypting API key in-memory."""
    from encryption import decrypt_api_key

    api_key = None
    if getattr(provider_record, "api_key", None):
        try:
            api_key = decrypt_api_key(provider_record.api_key)
        except Exception as e:
            logger.error(f"Failed to decrypt provider API key: {e}")
            raise HTTPException(status_code=400, detail="Invalid provider credentials")

    config_json = getattr(provider_record, "config_json", None)
    config = json.loads(config_json) if config_json else None

    return create_provider_from_config(
        provider_type=provider_record.provider_type,
        api_key=api_key,
        base_url=provider_record.base_url,
        model_id=provider_record.model_id,
        config=config,
        system_prompt=system_prompt,
        default_options=default_options,
    )
