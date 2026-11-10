"""Index sample metadata or send one validation question without exposing credentials."""
import argparse
import json
from pathlib import Path

import requests
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["index", "ask"])
    parser.add_argument("--question", default="How many customers are in samples_bank.customer?")
    args = parser.parse_args()
    values = dotenv_values(ROOT / ".env")
    auth = (values.get("DENODO_ADMIN_USER") or "admin", values.get("DENODO_ADMIN_PASSWORD"))
    if not auth[1]:
        raise SystemExit("Set DENODO_ADMIN_PASSWORD in .env")
    if args.operation == "index":
        response = requests.get("http://127.0.0.1:8008/getMetadata", auth=auth, params={
            "vdp_database_names": ["samples_bank"], "examples_per_table": 0,
        }, timeout=180)
    else:
        response = requests.post("http://127.0.0.1:8008/answerQuestion", auth=auth, json={
            "question": args.question, "vdp_database_names": ["samples_bank"], "check_ambiguity": False,
        }, timeout=180)
    response.raise_for_status()
    result = response.json()
    if args.operation == "index":
        print("Metadata indexed successfully; sample-row retrieval was disabled.")
    else:
        print(json.dumps({key: result[key] for key in ["answer", "sql_query", "execution_result"] if key in result}, indent=2))


if __name__ == "__main__":
    main()
