"""Load upstream sample banking views without requiring a cache datasource.

Refuses to overwrite an existing samples_bank database. Run before starting
the chatbot; the upstream import uses single-user mode temporarily.
"""
import sys
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
SDK = ROOT / ".runtime" / "sdk"
sys.path.insert(0, str(SDK))


def main():
    from adbc_driver_flightsql.dbapi import connect
    from utils.runner_demo import split_vql_statements, sync_vdp

    values = dotenv_values(ROOT / ".env")
    username = values.get("DENODO_ADMIN_USER") or "admin"
    password = values.get("DENODO_ADMIN_PASSWORD")
    if not password:
        raise SystemExit("Set DENODO_ADMIN_PASSWORD in .env")
    with connect("grpc://127.0.0.1:9994", db_kwargs={
        "username": username, "password": password,
        "adbc.flight.sql.rpc.call_header.database": "admin",
    }, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute("CALL GET_DATABASES();")
            if any(row[1] == "samples_bank" for row in cursor.fetchall()):
                raise SystemExit("samples_bank already exists; no views were changed. Use the existing database or a fresh environment.")
            vql = (SDK / "sample_chatbot/sample_data/structured/samples_bank.vql").read_text(encoding="utf-8")
            statements = split_vql_statements(vql)
            try:
                cursor.execute("METADATA ENCRYPTION PASSWORD 'denodo';")
                cursor.fetchall()
                count = 0
                for statement in statements:
                    statement = statement.strip()
                    if statement.startswith("SET 'com.denodo.vdb.cache.cacheStatus'") or statement.startswith("CREATE OR REPLACE DATASOURCE JDBC vdpcachedatasource") or statement.startswith("CHOWN admin DATASOURCE JDBC vdpcachedatasource"):
                        continue
                    cursor.execute(statement + ";")
                    cursor.fetchall()
                    count += 1
                print(f"Loaded {count} sample VQL statements (cache setup excluded).")
            finally:
                cursor.execute("EXIT SINGLE USER MODE;")
                cursor.fetchall()
                cursor.execute("METADATA ENCRYPTION DEFAULT;")
                cursor.fetchall()
    if not sync_vdp("http://127.0.0.1:9090", 1, username, password):
        raise SystemExit("Views loaded, but Data Marketplace sync failed; check its server registration and retry synchronization in its UI.")


if __name__ == "__main__":
    main()
