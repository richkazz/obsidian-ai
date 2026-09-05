"""Tests for Gemini JSON Schema adaptation and formatting."""

import json
from google.genai import types, _common
from google.genai.models import _GenerateContentParameters_to_mldev
from google.genai._api_client import BaseApiClient

from llm.schema_utils import (
    _strip_unsupported_gemini_keys,
    format_schema_dict_for_gemini,
    format_schema_for_gemini,
)
from llm.provider_factory import create_provider_from_config


def test_strip_unsupported_gemini_keys():
    raw_schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "$id": "https://example.com/schema.json",
        "title": "TestSchema",
        "type": "object",
        "properties": {
            "field_a": {
                "type": "string",
                "additionalProperties": False,
            },
            "field_b": {
                "type": "object",
                "properties": {
                    "nested": {"type": "integer"}
                },
                "additional_properties": False,
            },
        },
        "additionalProperties": False,
        "additional_properties": False,
    }

    cleaned = _strip_unsupported_gemini_keys(raw_schema)

    assert "$schema" not in cleaned
    assert "$id" not in cleaned
    assert "additionalProperties" not in cleaned
    assert "additional_properties" not in cleaned
    assert "additionalProperties" not in cleaned["properties"]["field_a"]
    assert "additional_properties" not in cleaned["properties"]["field_b"]


def test_format_schema_for_gemini_conversion():
    schema_dict = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer"},
            "meta": {
                "type": "object",
                "properties": {
                    "tags": {
                        "type": "array",
                        "items": {"type": "string", "additionalProperties": False},
                    }
                },
                "additional_properties": False,
            },
        },
        "required": ["name"],
        "additionalProperties": False,
    }

    formatted = format_schema_for_gemini(schema_dict)
    assert formatted is not None

    # Simulate google.genai request payload construction
    if not isinstance(formatted, dict):
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=formatted,
        )
    else:
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=formatted,
        )

    param = types._GenerateContentParameters(
        model="gemini-2.5-flash",
        contents="hello",
        config=config,
    )
    converted = _GenerateContentParameters_to_mldev(
        BaseApiClient(api_key="test"), param, None, param
    )
    dict_payload = _common.convert_to_dict(converted)
    gen_config = dict_payload.get("generationConfig", {})

    assert gen_config.get("responseMimeType") == "application/json"
    res_schema = gen_config.get("responseSchema", {})

    # Ensure no additional_properties / additionalProperties in final REST payload dict
    payload_str = json.dumps(res_schema)
    assert "additional_properties" not in payload_str
    assert "additionalProperties" not in payload_str
    assert "$schema" not in payload_str


def test_provider_factory_gemini_schema_propagation():
    agent = create_provider_from_config(
        provider_type="gemini",
        api_key="test_key",
        base_url=None,
        model_id="gemini-2.5-flash",
    )

    schema = {
        "type": "object",
        "properties": {
            "result": {"type": "string", "additional_properties": False}
        },
        "additionalProperties": False,
    }

    formatted = format_schema_for_gemini(schema)
    opts = {}
    if isinstance(formatted, dict):
        opts["response_format"] = formatted
    else:
        opts["response_schema"] = formatted

    prepared_config = agent.client._prepare_config(opts, None)
    assert prepared_config.response_schema is not None

    param = types._GenerateContentParameters(
        model="gemini-2.5-flash",
        contents="hello",
        config=prepared_config,
    )
    converted = _GenerateContentParameters_to_mldev(
        BaseApiClient(api_key="test"), param, None, param
    )
    dict_payload = _common.convert_to_dict(converted)

    payload_str = json.dumps(dict_payload)
    assert "additional_properties" not in payload_str
    assert "additionalProperties" not in payload_str
