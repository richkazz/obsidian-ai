import pytest
import asyncio
from tracing_service import TraceContext, SpanData, DatabaseTraceProvider, OtelTraceProvider, NoopTraceProvider

@pytest.mark.asyncio
async def test_trace_context_and_span_creation():
    ctx = TraceContext(session_id="123")
    assert ctx.trace_id is not None
    assert ctx.current_span_id is None

    span1 = ctx.create_span("root_span", span_type="agent_run")
    assert span1.trace_id == ctx.trace_id
    assert span1.parent_span_id is None

    ctx.span_stack.append(span1.span_id)
    assert ctx.current_span_id == span1.span_id

    span2 = ctx.create_span("child_span", span_type="llm_call")
    assert span2.trace_id == ctx.trace_id
    assert span2.parent_span_id == span1.span_id

    span2.finish(status="success")
    assert span2.duration_ms >= 0
    assert "process_rss_bytes" in span2.attributes

@pytest.mark.asyncio
async def test_noop_provider():
    provider = NoopTraceProvider()
    ctx = TraceContext()
    span = ctx.create_span("noop_test")
    await provider.export_span(span)
    await provider.flush()
