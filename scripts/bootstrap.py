"""Fetch a pinned upstream SDK and apply the local exporter hook."""
import argparse
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SDK = ROOT / ".runtime" / "sdk"
SDK_COMMIT = "891d83edfc9f2f5984d285b7723abb3079aaa27c"
SDK_URL = "https://github.com/denodo/denodo-ai-sdk.git"


def patch_tracing(source):
    marker = "from utils.agent_management_otel import AgentManagementExporter"
    if marker in source:
        return source
    anchor = "        _client = Langfuse(release=AI_SDK_VERSION)"
    if source.count(anchor) != 1:
        raise RuntimeError("Unexpected upstream tracing code; refusing to patch it")
    return source.replace(anchor, "\n".join([
        "        if os.getenv('DENODO_AM_EXPORT') == '1':",
        "            from utils.agent_management_otel import AgentManagementExporter",
        "            _client = Langfuse(release=AI_SDK_VERSION, span_exporter=AgentManagementExporter())",
        "        else:",
        "            _client = Langfuse(release=AI_SDK_VERSION)",
    ]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", default="3.12", help="Python selector passed to uv")
    parser.add_argument("--skip-install", action="store_true")
    args = parser.parse_args()
    for binary in ["git"] + ([] if args.skip_install else ["uv"]):
        if not shutil.which(binary):
            raise SystemExit(f"Install {binary} before running bootstrap")
    SDK.parent.mkdir(parents=True, exist_ok=True)
    if not SDK.exists():
        subprocess.run(["git", "clone", "--filter=blob:none", "--no-checkout", SDK_URL, str(SDK)], check=True)
        subprocess.run(["git", "-C", str(SDK), "checkout", "--detach", SDK_COMMIT], check=True)
    current = subprocess.check_output(["git", "-C", str(SDK), "rev-parse", "HEAD"], text=True).strip()
    if current != SDK_COMMIT:
        raise SystemExit("Existing SDK checkout is not the pinned revision; no changes made")
    target = SDK / "utils" / "langfuse.py"
    target.write_text(patch_tracing(target.read_text(encoding="utf-8")), encoding="utf-8")
    shutil.copy2(ROOT / "adapters" / "agent_management_otel.py", SDK / "utils" / "agent_management_otel.py")
    if not args.skip_install:
        interpreter = SDK / ".venv" / "bin" / "python"
        if not interpreter.exists():
            subprocess.run(["uv", "venv", str(SDK / ".venv"), "--python", args.python], check=True)
        subprocess.run(["uv", "pip", "install", "--python", str(interpreter), "-r", str(ROOT / "requirements-openai.txt")], check=True)
    print("Pinned SDK ready. Next: configure .env and run scripts/configure.py with the SDK Python.")


if __name__ == "__main__":
    main()
