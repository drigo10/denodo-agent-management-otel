# Troubleshooting

## Docker login is unauthorized

Browser OIDC login and Docker authentication are separate. Use the username and **CLI secret** from your Harbor user profile. Do not use the website password. If the secret no longer works, sign out/in through the OIDC provider and regenerate the CLI secret in Harbor.

## Container starts slowly or exits

Check `docker compose ps` and `docker compose logs --tail=100 denodo`. The pinned AMD64 image uses emulation on Apple Silicon. Check Docker resources, license validity, file-mount access, and occupied ports. Wait for database health rather than assuming a started container is ready.

## Sample loader fails on cache configuration

The supplied loader excludes the upstream cache setup and indexes metadata without sample rows. Do not run the unmodified upstream `--load-demo` path unless you also configure the required cache datasource. If `samples_bank` already exists, the loader refuses to replace it. Inspect the existing database rather than dropping it automatically. On a partially imported fresh test environment, resolve the failed statement before deciding how to reset the data.

## Agent is discovered but the traces dataset is empty

Check each stage:

1. Exporter response: did OTLP delivery succeed?
2. Receiver logs: did AM receive the export?
3. Monitoring: is the exact `service.name` configured with a target dataset?
4. Semantic-convention logs: is AM accepting or ignoring the trace format?
5. Buffer: has the receiver's idle interval elapsed?
6. Dataset sample: has Explore refreshed since data was written?
7. Derived data: have conversation/metric datasets been built?

Traces before monitoring can be dropped with a no-target-dataset message. Send a new request after monitoring is enabled.

In native mode, the tested receiver logged that traces did not use a supported agent semantic convention. Switch to mapped mode, regenerate configuration, restart the Python services, and send another question. Keep the original payload to understand the difference.

## “Root path does not exist” in Explore

This can mean no files have been written yet. It is not by itself proof of a broken storage connection. In the reference test, the receiver had discarded native traces; accepted mapped traces subsequently created stored rows. First check receiver retention/write logs, then refresh Explore or update its sample. If the logs show write failures, investigate the configured storage connection and execution user.

## User is null

Inspect raw telemetry before changing permissions or adding a hardcoded username:

- If identity is absent from the original trace, inspect application authentication and tracing context.
- If identity is present but the stored column is null, inspect receiver parsing, attribute placement and root selection.
- A service account can represent the caller at the data layer without identifying the human chatting with the application.

The pinned SDK extracts Basic-auth usernames from credentials and JWT identity from claims. Opaque bearer tokens use a Denodo session-user lookup. A failed lookup can leave identity unresolved. The standard-user path was tested; other authentication paths require separate validation.

## `INPUT_DATA_VERY_LONG` warning

This is a dataset-reading warning about unusually large cell content. A nested trace can legitimately be large. Incorrect CSV quoting can also produce oversized fields. The warning alone does not prove quoting corruption, stored-value truncation or the cause of missing user data. Parse the full affected trace value and check row/column alignment before modifying format settings or truncating payloads. The adapter retains original fields alongside normalized messages, which can increase the size.

## Cost is empty or one question has several rows

Row retention does not establish model-cost attribution. Inspect actual token/model/provider fields and configure matching model pricing in AM. The SDK can emit separate pipeline traces for one question, so interaction-row count may exceed question count. This repository does not collapse them into a single request trace.

## SDK process disappeared after launch

Use the foreground command in the README and leave its terminal open. The process lifetime of background launches depends on the host/session manager. Use a proper service supervisor if you need unattended operation.
