"""Traces: OpenTelemetry spans for debugging, never for evidence, which is the ledger.

The core's calls go out as spans, using the GenAI conventions at a pinned version, since
they're still at Development stability: each run opening, model call, tool call and message.
Spans are masked by what they leave out: no prompt, reply, message or tool argument, and no
person, only what a call was, how it was decided, how long it took, and its tokens. They go
to the OpenTelemetry endpoint the deployment names in OTEL_EXPORTER_OTLP_ENDPOINT, kept
there for 14 days [TBC], and nowhere if it names none.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor, SpanExporter
from opentelemetry.trace import Status, StatusCode

SCHEMA = "https://opentelemetry.io/schemas/1.37.0"  # the GenAI conventions a5s follows, pinned
_provider: TracerProvider | None = None


def setup(service: str, exporter: SpanExporter | None = None, *, at_once: bool = False) -> bool:
    """Send this part's spans to the deployment's endpoint, or to `exporter`. Whether they go
    anywhere: without an endpoint, spans cost nothing and go nowhere."""
    global _provider
    if exporter is None:
        if not (os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
                or os.environ.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")):
            return False
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        exporter = OTLPSpanExporter()
    _provider = TracerProvider(resource=Resource.create({"service.name": service}))
    _provider.add_span_processor(SimpleSpanProcessor(exporter) if at_once
                                 else BatchSpanProcessor(exporter))
    return True


@contextmanager
def span(name: str, **attributes: Any) -> Iterator[trace.Span]:
    """A span for one of the core's calls, around the call, so it says how long it took, with
    only the attributes given, none of them None. A call that fails is marked with the kind of
    failure alone, never its message, which can carry what the call was given; one the core
    refuses, such as a run that doesn't open, with its HTTP status."""
    tracer = (_provider or trace.get_tracer_provider()).get_tracer("a5s", schema_url=SCHEMA)
    with tracer.start_as_current_span(name, record_exception=False,
                                      set_status_on_exception=False) as current:
        note(current, **attributes)
        try:
            yield current
        except Exception as exc:
            code = getattr(exc, "status_code", None)
            if isinstance(code, int) and code < 500:
                current.set_attribute("http.response.status_code", code)
            else:
                current.set_attribute("error.type", type(exc).__name__)
                current.set_status(Status(StatusCode.ERROR))
            raise


def note(current: trace.Span, **attributes: Any) -> None:
    """Add what's known later in a call to its span, leaving out any that are None."""
    current.set_attributes({k: v for k, v in attributes.items() if v is not None})
