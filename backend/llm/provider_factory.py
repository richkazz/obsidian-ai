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

from .base import LLMStreamChunk, LLMToolCall, to_maf_messages
from .nvidia_provider import NvidiaProvider
from .schema_utils import format_schema_for_gemini

logger = logging.getLogger(__name__)


def _usage_from_update(update) -> dict:
    usage = getattr(update, "usage_details", None)
    if usage is None:
        return {}
    return {
        key: value
        for key, value in {
            "input_tokens": getattr(usage, "input_token_count", None),
            "output_tokens": getattr(usage, "output_token_count", None),
            "cache_creation_input_tokens": getattr(usage, "cache_creation_input_token_count", None),
            "cache_read_input_tokens": getattr(usage, "cache_read_input_token_count", None),
        }.items()
        if value is not None
    }


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

        if hasattr(self.client, "get_response") and callable(self.client.get_response):
            messages = args[0] if args else kwargs.pop("messages")
            system_prompt = kwargs.pop("system_prompt", None)
            tools = kwargs.pop("tools", None)
            response_schema = kwargs.pop("response_schema", None)
            options = dict(kwargs.pop("options", {}) or {})
            if system_prompt:
                options["instructions"] = system_prompt
            if tools:
                options["tools"] = tools
            if response_schema:
                if isinstance(self.client, GeminiChatClient) or getattr(self.client, "provider_type", None) in ("google", "gemini"):
                    formatted = format_schema_for_gemini(response_schema)
                    if isinstance(formatted, dict):
                        options["response_format"] = formatted
                    else:
                        options["response_schema"] = formatted
                else:
                    options["response_format"] = response_schema

            stream = self.client.get_response(
                to_maf_messages(messages),
                stream=True,
                options=options or None,
                **kwargs,
            )
            if inspect.isawaitable(stream):
                stream = await stream

            emitted_done = False
            tool_calls = {}
            async for update in stream:
                for content in getattr(update, "contents", []):
                    content_type = getattr(content, "type", None)
                    if content_type == "text" and getattr(content, "text", None):
                        yield LLMStreamChunk(type="content", content=content.text)
                    elif content_type == "text_reasoning" and getattr(content, "text", None):
                        yield LLMStreamChunk(type="reasoning", reasoning=content.text)
                    elif content_type in ("function_call", "tool_call"):
                        arguments = getattr(content, "arguments", {})
                        if not isinstance(arguments, str):
                            arguments = json.dumps(arguments)
                        call_id = getattr(content, "call_id", None) or getattr(content, "id", "")
                        call = tool_calls.setdefault(call_id, {"id": call_id, "name": "", "arguments": ""})
                        call["name"] = getattr(content, "name", "") or call["name"]
                        call["arguments"] += arguments

                finish_reason = getattr(update, "finish_reason", None)
                if finish_reason:
                    for call in tool_calls.values():
                        yield LLMStreamChunk(type="tool_call", tool_call=LLMToolCall(**call))
                    tool_calls.clear()
                    emitted_done = True
                    yield LLMStreamChunk(
                        type="done",
                        finish_reason=finish_reason,
                        usage=_usage_from_update(update),
                    )

            if not emitted_done:
                for call in tool_calls.values():
                    yield LLMStreamChunk(type="tool_call", tool_call=LLMToolCall(**call))
                yield LLMStreamChunk(type="done", finish_reason="stop")
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
