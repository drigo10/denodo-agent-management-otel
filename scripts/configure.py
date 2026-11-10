"""Generate ignored SDK configuration files from the repository's private .env."""
import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
SDK = ROOT / ".runtime" / "sdk"


def validate(values):
    required = ["OPENAI_API_KEY", "DENODO_LICENSE_FILE", "DENODO_ADMIN_PASSWORD", "AM_OTLP_TRACES_ENDPOINT", "AM_API_KEY"]
    missing = [key for key in required if not values.get(key) or "replace-with" in values[key]]
    if missing:
        raise ValueError("Set these .env values: " + ", ".join(missing))
    license_file = Path(values["DENODO_LICENSE_FILE"]).expanduser()
    if not license_file.is_absolute() or not license_file.is_file():
        raise ValueError("DENODO_LICENSE_FILE must be an existing absolute file path")
    endpoint = urlsplit(values["AM_OTLP_TRACES_ENDPOINT"])
    if endpoint.scheme != "https" or not endpoint.hostname or endpoint.hostname.endswith(".example"):
        raise ValueError("Use the HTTPS trace endpoint from your AM receiver setup panel")
    if endpoint.username or endpoint.password or endpoint.query or endpoint.fragment:
        raise ValueError("Keep credentials in AM_API_KEY; use a plain receiver endpoint URL")
    if values.get("DENODO_AM_NORMALIZE", "1") not in {"0", "1"}:
        raise ValueError("DENODO_AM_NORMALIZE must be 0 or 1")


def main():
    values = dotenv_values(ROOT / ".env")
    validate(values)
    data_dir = SDK / "local-data"
    data_dir.mkdir(parents=True, exist_ok=True)
    model = values.get("OPENAI_MODEL") or "gpt-4o-mini"
    embedding = values.get("OPENAI_EMBEDDING_MODEL") or "text-embedding-3-small"
    common = {
        "OPENAI_API_KEY": values["OPENAI_API_KEY"], "AI_SDK_DATA_DIR": str(data_dir),
        "DENODO_AM_EXPORT": "1", "DENODO_AM_NORMALIZE": values.get("DENODO_AM_NORMALIZE", "1"),
        "OTEL_SERVICE_NAME": values.get("OTEL_SERVICE_NAME") or "denodo-ai-sdk",
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": values["AM_OTLP_TRACES_ENDPOINT"],
        "OTEL_EXPORTER_OTLP_TRACES_HEADERS": "Authorization=Bearer " + values["AM_API_KEY"],
        "OTEL_EXPORTER_OTLP_TRACES_PROTOCOL": "http/protobuf",
        # Local identifiers initialize Langfuse callbacks. No Langfuse account/server is used.
        "LANGFUSE_PUBLIC_KEY": "local-denodo-otel", "LANGFUSE_SECRET_KEY": "unused-local-export",
        "LANGFUSE_BASE_URL": "http://127.0.0.1:8008", "LANGFUSE_MEDIA_UPLOAD_ENABLED": "false",
        "LANGFUSE_FLUSH_INTERVAL": "1",
    }
    configs = {
        "api/utils/sdk_config.env": {
            "AI_SDK_HOST": "127.0.0.1", "AI_SDK_PORT": "8008",
            "AI_SDK_DATA_MARKETPLACE_URL": "http://127.0.0.1:9090/denodo-data-catalog/",
            "LLM_PROVIDER": "OpenAI", "LLM_MODEL": model,
            "EMBEDDINGS_PROVIDER": "OpenAI", "EMBEDDINGS_MODEL": embedding,
            "THINKING_LLM_PROVIDER": "", "THINKING_LLM_MODEL": "", "VECTOR_STORE": "Chroma",
        },
        "sample_chatbot/chatbot_config.env": {
            "CHATBOT_HOST": "127.0.0.1", "CHATBOT_PORT": "9992",
            "CHATBOT_LLM_PROVIDER": "OpenAI", "CHATBOT_LLM_MODEL": model,
            "CHATBOT_EMBEDDINGS_PROVIDER": "OpenAI", "CHATBOT_EMBEDDINGS_MODEL": embedding,
            "CHATBOT_VECTOR_STORE_PROVIDER": "Chroma", "CHATBOT_DATABASE_PROVIDER": "SQLite",
            "CHATBOT_DEEPQUERY": "0", "AI_SDK_URL": "http://127.0.0.1:8008",
        },
    }
    for relative, overrides in configs.items():
        target = SDK / relative
        settings = dotenv_values(str(target) + ".example")
        settings.update(common)
        settings.update(overrides)
        target.write_text("".join(f"{key}={value!r}\n" for key, value in settings.items() if value is not None), encoding="utf-8")
        os.chmod(target, 0o600)
    os.chmod(ROOT / ".env", 0o600)
    print("SDK configuration written; secret values were not displayed. Next: docker compose up -d")


if __name__ == "__main__":
    main()
