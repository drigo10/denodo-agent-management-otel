import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExportResult
from opentelemetry.trace import SpanContext, TraceFlags

ROOT = Path(__file__).resolve().parents[1]


def module_at(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


adapter = module_at("adapter", "adapters/agent_management_otel.py")
bootstrap = module_at("bootstrap", "scripts/bootstrap.py")
configure = module_at("configure", "scripts/configure.py")


def make_span(attributes, parent=None):
    return ReadableSpan(
        name="ChatOpenAI", context=SpanContext(123, 456, False, TraceFlags(1)),
        parent=parent, resource=Resource.create({"service.name": "test-agent"}),
        attributes=attributes, start_time=100, end_time=200,
    )


class MappingTests(unittest.TestCase):
    def test_generation_preserves_original_identity_and_usage(self):
        attrs = {
            "langfuse.observation.type": "generation", "user.id": "analyst",
            "session.id": "session-one", "langfuse.observation.model.name": "example-model",
            "langfuse.observation.metadata.ls_provider": "openai",
            "langfuse.observation.usage_details": '{"input":11,"output":7}',
            "langfuse.observation.input": '[{"role":"user","content":"hello"}]',
        }
        parent = SpanContext(123, 789, False, TraceFlags(1))
        original = make_span(attrs, parent)
        mapped = adapter.normalize_span(original)
        self.assertEqual(mapped.context, original.context)
        self.assertEqual(mapped.parent, parent)
        self.assertEqual((mapped.start_time, mapped.end_time), (100, 200))
        self.assertEqual(mapped.resource, original.resource)
        self.assertEqual(mapped.attributes["user.id"], "analyst")
        self.assertEqual(mapped.attributes["gen_ai.conversation.id"], "session-one")
        self.assertEqual(mapped.attributes["gen_ai.usage.input_tokens"], 11)
        self.assertEqual(mapped.attributes["gen_ai.usage.output_tokens"], 7)
        self.assertNotIn("gen_ai.operation.name", original.attributes)
        self.assertEqual(json.loads(mapped.attributes["gen_ai.input.messages"])[0]["parts"][0]["content"], "hello")

    def test_existing_genai_values_win(self):
        mapped = adapter.normalize_span(make_span({
            "langfuse.observation.type": "generation", "gen_ai.operation.name": "chat",
            "gen_ai.request.model": "original-model", "langfuse.observation.model.name": "other-model",
        }))
        self.assertEqual(mapped.attributes["gen_ai.request.model"], "original-model")

    def test_missing_identity_and_bad_usage_are_not_invented(self):
        mapped = adapter.normalize_span(make_span({
            "langfuse.observation.type": "generation", "langfuse.observation.usage_details": "not-json",
        }))
        self.assertNotIn("user.id", mapped.attributes)
        self.assertNotIn("gen_ai.usage.input_tokens", mapped.attributes)
        self.assertNotIn("gen_ai.provider.name", mapped.attributes)

    def test_root_chains_are_invocations_but_nested_chains_are_generic(self):
        root = make_span({"langfuse.observation.type": "chain"})
        child = make_span({"langfuse.observation.type": "chain"}, SpanContext(123, 789, False, TraceFlags(1)))
        self.assertEqual(adapter.normalize_span(root).attributes["gen_ai.operation.name"], "invoke_agent")
        self.assertNotIn("gen_ai.operation.name", adapter.normalize_span(child).attributes)

    def test_tool_values_are_preserved(self):
        mapped = adapter.normalize_span(make_span({
            "langfuse.observation.type": "tool", "langfuse.observation.input": '{"query":"SELECT 1"}',
            "langfuse.observation.output": "1",
        }))
        self.assertEqual(mapped.attributes["gen_ai.operation.name"], "execute_tool")
        self.assertEqual(mapped.attributes["gen_ai.tool.call.arguments"], '{"query":"SELECT 1"}')

    def test_native_and_mapped_captures_remain_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            remote = Mock()
            remote.export.return_value = SpanExportResult.SUCCESS
            with patch.dict(os.environ, {"AI_SDK_DATA_DIR": directory, "DENODO_AM_NORMALIZE": "1"}), patch.object(adapter, "OTLPSpanExporter", return_value=remote):
                exporter = adapter.AgentManagementExporter()
                original = make_span({"langfuse.observation.type": "generation"})
                self.assertEqual(exporter.export([original]), SpanExportResult.SUCCESS)
                raw = Path(directory, "telemetry/otlp-batches.jsonl").read_text()
                mapped = Path(directory, "telemetry/otlp-batches-genai.jsonl").read_text()
                self.assertNotIn('"key":"gen_ai.operation.name"', raw)
                self.assertIn('"key":"gen_ai.operation.name"', mapped)
                self.assertNotIn("gen_ai.operation.name", original.attributes)

    def test_native_mode_does_not_normalize(self):
        with tempfile.TemporaryDirectory() as directory:
            remote = Mock()
            remote.export.return_value = SpanExportResult.SUCCESS
            with patch.dict(os.environ, {"AI_SDK_DATA_DIR": directory, "DENODO_AM_NORMALIZE": "0"}), patch.object(adapter, "OTLPSpanExporter", return_value=remote):
                exporter = adapter.AgentManagementExporter()
                original = make_span({"langfuse.observation.type": "generation"})
                exporter.export([original])
                self.assertIs(remote.export.call_args.args[0][0], original)
                self.assertFalse(Path(directory, "telemetry/otlp-batches-genai.jsonl").exists())


class SetupTests(unittest.TestCase):
    def test_patch_is_idempotent_and_refuses_unknown_source(self):
        source = "def init():\n        _client = Langfuse(release=AI_SDK_VERSION)\n"
        once = bootstrap.patch_tracing(source)
        self.assertEqual(bootstrap.patch_tracing(once), once)
        with self.assertRaises(RuntimeError):
            bootstrap.patch_tracing("unknown upstream initialization")

    def test_placeholder_configuration_is_rejected(self):
        with self.assertRaises(ValueError):
            configure.validate({"OPENAI_API_KEY": "replace-with-your-openai-key"})

    def test_valid_configuration_and_credential_url_rejection(self):
        with tempfile.NamedTemporaryFile() as license_file:
            values = {
                "OPENAI_API_KEY": "test-placeholder", "DENODO_LICENSE_FILE": license_file.name,
                "DENODO_ADMIN_PASSWORD": "test-placeholder", "AM_API_KEY": "test-placeholder",
                "AM_OTLP_TRACES_ENDPOINT": "https://receiver.example.org/dip/api/otlp/test/v1/traces",
            }
            configure.validate(values)
            values["AM_OTLP_TRACES_ENDPOINT"] = "https://user:password@receiver.example.org/v1/traces"
            with self.assertRaises(ValueError):
                configure.validate(values)


if __name__ == "__main__":
    unittest.main()
