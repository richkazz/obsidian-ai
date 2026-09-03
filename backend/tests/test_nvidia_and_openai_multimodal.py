import os
import pytest
from llm.base import LLMMessage
from llm.nvidia import NVIDIANIMProvider
from llm.openai_provider import OpenAIProvider
from llm.provider_factory import create_provider_from_config


def test_openai_build_payload_extended_parameters():
    provider = OpenAIProvider(
        api_key="test-key",
        model_id="gpt-4o",
        config={
            "temperature": 0.7,
            "max_tokens": 1000,
            "top_p": 0.9,
            "stop": ["\n"],
            "seed": 42,
            "frequency_penalty": 0.5,
            "presence_penalty": 0.2,
            "reasoning_effort": "high",
            "top_k": 50,
            "unsupported_key": "ignored",
            "none_key": None,
        },
    )

    messages = [
        LLMMessage(
            role="user",
            content=[
                {"type": "text", "text": "What is in this image?"},
                {
                    "type": "image_url",
                    "image_url": {"url": "https://example.com/image.jpg"},
                },
            ],
        )
    ]

    payload = provider._build_payload(messages, system_prompt="You are helpful.", stream=True)

    assert payload["model"] == "gpt-4o"
    assert payload["stream"] is True
    assert payload["stream_options"] == {"include_usage": True}
    assert payload["temperature"] == 0.7
    assert payload["max_tokens"] == 1000
    assert payload["top_p"] == 0.9
    assert payload["stop"] == ["\n"]
    assert payload["seed"] == 42
    assert payload["frequency_penalty"] == 0.5
    assert payload["presence_penalty"] == 0.2
    assert payload["reasoning_effort"] == "high"
    assert payload["top_k"] == 50
    assert "unsupported_key" not in payload
    assert "none_key" not in payload

    # Verify multimodal messages structure passed through unchanged
    assert payload["messages"][0] == {"role": "system", "content": "You are helpful."}
    assert payload["messages"][1]["role"] == "user"
    assert isinstance(payload["messages"][1]["content"], list)
    assert len(payload["messages"][1]["content"]) == 2


def test_nvidia_nim_provider_init_and_env_api_key(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test-123")

    provider = NVIDIANIMProvider(model_id="moonshotai/kimi-k3")

    assert provider.api_key == "nvapi-test-123"
    assert provider.base_url == "https://integrate.api.nvidia.com/v1"
    assert provider.model_id == "moonshotai/kimi-k3"

    # Direct api_key parameter overrides env
    provider_custom = NVIDIANIMProvider(
        api_key="nvapi-override",
        base_url="http://localhost:8000/v1",
        model_id="nvidia/nemotron-3-ultra-550b-a55b",
    )
    assert provider_custom.api_key == "nvapi-override"
    assert provider_custom.base_url == "http://localhost:8000/v1"


def test_nvidia_nim_provider_missing_api_key(monkeypatch):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)

    with pytest.raises(ValueError, match="NVIDIA_API_KEY is missing"):
        NVIDIANIMProvider()


@pytest.mark.asyncio
async def test_nvidia_nim_provider_get_context_length():
    provider = NVIDIANIMProvider(api_key="test-key")
    ctx_len = await provider.get_context_length()
    assert ctx_len is None


def test_provider_factory_nvidia_registration():
    provider = create_provider_from_config(
        provider_type="nvidia",
        api_key="nvapi-factory-test",
        base_url=None,
        model_id="deepseek-ai/deepseek-v4-pro-0813",
        config={"reasoning_effort": "max"},
    )

    assert isinstance(provider, NVIDIANIMProvider)
    assert provider.api_key == "nvapi-factory-test"
    assert provider.base_url == "https://integrate.api.nvidia.com/v1"
    assert provider.config.get("reasoning_effort") == "max"

    provider_nim = create_provider_from_config(
        provider_type="nvidia_nim",
        api_key="nvapi-factory-test-2",
        base_url=None,
        model_id="nvidia/nemotron-3-ultra-550b-a55b",
    )
    assert isinstance(provider_nim, NVIDIANIMProvider)


def test_openai_url_formatting():
    provider = OpenAIProvider(api_key="key", base_url="https://integrate.api.nvidia.com/v1")
    assert provider._url("v1/chat/completions") == "https://integrate.api.nvidia.com/v1/chat/completions"
    assert provider._url("models") == "https://integrate.api.nvidia.com/v1/models"

    provider_no_v1 = OpenAIProvider(api_key="key", base_url="https://api.openai.com")
    assert provider_no_v1._url("v1/chat/completions") == "https://api.openai.com/v1/chat/completions"
