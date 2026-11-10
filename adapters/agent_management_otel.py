"""Transport native Langfuse spans to AM and retain the OTLP payload locally.

Native spans are always captured before optional GenAI attribute translation.
The translation preserves identity, timing, hierarchy and original attributes.
"""
import json
import logging
import os
import threading
from pathlib import Path

from google.protobuf.json_format import MessageToDict
from opentelemetry.exporter.otlp.proto.common.trace_encoder import encode_spans
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import SpanExporter
from opentelemetry.sdk.trace import ReadableSpan


def _json(value):
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return value


def _messages(value, role):
    value = _json(value)
    if value is None:
        return None
    items = value if isinstance(value, list) else [value]
    messages = []
    for item in items:
        item_role = item.get('role', role) if isinstance(item, dict) else role
        content = item.get('content', item.get('text', item)) if isinstance(item, dict) else item
        if isinstance(content, list):
            text = '\n'.join(part.get('text', '') if isinstance(part, dict) else str(part) for part in content)
        else:
            text = content if isinstance(content, str) else json.dumps(content, default=str)
        messages.append({'role': item_role, 'parts': [{'type': 'text', 'content': text}]})
    return json.dumps(messages)


def normalize_span(span):
    attrs = dict(span.attributes or {})
    kind = attrs.get('langfuse.observation.type')
    if kind == 'generation':
        attrs.setdefault('gen_ai.operation.name', 'chat')
    elif kind == 'tool':
        attrs.setdefault('gen_ai.operation.name', 'execute_tool')
        attrs.setdefault('gen_ai.tool.name', span.name)
        for suffix, target in [('input', 'arguments'), ('output', 'result')]:
            value = attrs.get('langfuse.observation.' + suffix)
            if value is not None:
                attrs.setdefault('gen_ai.tool.call.' + target, value)
    elif kind in {'agent', 'chain'} and span.parent is None:
        # SDK pipeline roots represent invocations; nested chains stay generic.
        attrs.setdefault('gen_ai.operation.name', 'invoke_agent')
        attrs.setdefault('gen_ai.agent.name', os.getenv('OTEL_SERVICE_NAME', 'denodo-ai-sdk'))

    if attrs.get('session.id'):
        attrs.setdefault('gen_ai.conversation.id', attrs['session.id'])
    if attrs.get('gen_ai.operation.name') in {'invoke_agent', 'chat'}:
        for suffix, role in [('input', 'user'), ('output', 'assistant')]:
            value = _messages(attrs.get('langfuse.observation.' + suffix), role)
            if value is not None:
                attrs.setdefault('gen_ai.' + suffix + '.messages', value)
    if kind == 'generation':
        model = attrs.get('langfuse.observation.model.name')
        if model:
            attrs.setdefault('gen_ai.request.model', model)
            attrs.setdefault('gen_ai.response.model', model)
        provider = attrs.get('langfuse.observation.metadata.ls_provider')
        if provider:
            attrs.setdefault('gen_ai.provider.name', provider)
        usage = _json(attrs.get('langfuse.observation.usage_details'))
        if isinstance(usage, dict):
            for source, target in [('input', 'input_tokens'), ('output', 'output_tokens')]:
                if isinstance(usage.get(source), int):
                    attrs.setdefault('gen_ai.usage.' + target, usage[source])
    attrs['denodo.am.mapping.version'] = 'langfuse-to-genai-v1'
    return ReadableSpan(
        name=span.name, context=span.context, parent=span.parent,
        resource=span.resource, attributes=attrs, events=span.events,
        links=span.links, kind=span.kind, status=span.status,
        start_time=span.start_time, end_time=span.end_time,
        instrumentation_scope=span.instrumentation_scope,
    )


class AgentManagementExporter(SpanExporter):
    def __init__(self):
        self._remote = OTLPSpanExporter()
        self._lock = threading.Lock()
        self._path = Path(os.environ['AI_SDK_DATA_DIR']) / 'telemetry' / 'otlp-batches.jsonl'
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._normalize = os.getenv('DENODO_AM_NORMALIZE') == '1'

    def _capture(self, spans, path):
        payload = MessageToDict(encode_spans(spans))
        with self._lock:
            with path.open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(payload, separators=(',', ':')) + '\n')

    def export(self, spans):
        self._capture(spans, self._path)
        if self._normalize:
            spans = [normalize_span(span) for span in spans]
            self._capture(spans, self._path.with_name('otlp-batches-genai.jsonl'))
        result = self._remote.export(spans)
        logging.info('AM OTLP export: %s (%d spans)', result.name, len(spans))
        return result

    def shutdown(self):
        self._remote.shutdown()

    def force_flush(self, timeout_millis=30000):
        return self._remote.force_flush(timeout_millis)
