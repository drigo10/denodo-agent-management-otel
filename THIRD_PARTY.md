# Third-party components

No license file has been selected for this repository's own integration code. This does not change any upstream component's license.

- **Denodo AI SDK** is maintained by Denodo at <https://github.com/denodo/denodo-ai-sdk>. Bootstrap fetches commit `891d83edfc9f2f5984d285b7723abb3079aaa27c` into an ignored local directory. The SDK and its sample data are not bundled in this repository. Preserve and review the upstream license/notices in that checkout. Its root `LICENSE.txt` identifies Apache License 2.0; component-level notices remain applicable to their respective files.
- **Denodo Platform** is obtained from Denodo's Harbor registry and requires your own valid platform license. No platform image, entitlement, license file or account is redistributed here.
- **Python dependencies** such as LangChain, LangGraph, Langfuse and OpenTelemetry retain their own licenses. The requirements files specify dependencies; they do not relicense them.
- **Dataiku Agent Management** and **OpenAI** are external services configured by the person running the integration. Their software, accounts, credentials and service terms are outside this repository's license.

Bootstrap makes a local initialization change to the SDK's `utils/langfuse.py` to select this repository's exporter. It keeps the upstream checkout and license files separate. The adapter and setup scripts are independent integration code. Product names identify integration targets; this repository is not an official product connector or endorsement.
