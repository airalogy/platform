# Platform and Masterbrain AI boundary

Platform uses the published `masterbrain==0.12.0` Python package for built-in model calls, including text embeddings. It does not require a separate AI service in the default package mode. This unifies model access, not ownership of the research system.

| Layer | Owns |
| --- | --- |
| Masterbrain | Reusable AI capabilities, provider clients, model request/response validation and per-call usage events. |
| Platform | Identity, authorization, trusted context selection, operational budgets, approvals, durable assets, audit and execution state. |
| Instrument Gateway / Compute Runner | Explicitly authorized execution and independent result/stop observations. |

Prompts and context assembly that depend on Platform objects remain in Platform. A model response cannot grant access, approve itself, write a final asset or authorize an instrument operation. Built-in provider SDK imports in API product code are guarded by an offline regression test; integration goes through `app/libs/masterbrain.py`. Protocol executor code supplied by users is a separate execution boundary, not a built-in model capability.

## Embeddings and non-AI search

- The index contract remains Qwen `text-embedding-v4`, 1024 dimensions, at most six texts per call. Changing only a model setting would mix incompatible vector spaces; a model change requires an explicit reindex migration.
- Protocol and discussion indexing, public Hub retrieval and chat retrieval now use the same Masterbrain embedding endpoint. Requests carry server-derived usage context; interactive callers supply the authorized user and Lab/Project, while internal Hub retrieval identifies an internal service rather than inventing a user.
- `AI_ENABLED=false` prevents embedding model requests. A GPT-only configuration does not silently substitute an OpenAI embedding model. Missing Qwen capability, model failure or invalid embedding responses leave the local keyword path available.
- Keyword-only chunks store a nullable vector, never a zero vector or fabricated similarity score. Existing vectors remain intact during the schema upgrade. Keyword-only rows also remain searchable after AI recovers.
- Resource index replacement commits deletion and insertion together. Public recommendations exclude private Projects, protocol-level permission Projects, and deleted Projects/Protocols; scoped discussion retrieval retains its Protocol boundary. Retrieval does not grant access to the source asset.
- Model calls do not log raw research text or provider error bodies. Provider-reported tokens are metered; an unavailable price remains unknown rather than being reported as free. Cancelled calls remain cancelled.

This fallback covers the Protocol/discussion embedding index. Knowledge, Record and other deterministic search interfaces retain their existing implementations; the change does not add an AI requirement to them.

## Deployment and migration

Install the locked production dependency and run the normal database migration before starting the upgraded API. Revision `0058_optional_embeddings` makes only the embedding column nullable; it does not delete text or rewrite existing vectors.

External mode (`MASTERBRAIN_CALL_MODE=external`) needs a compatible Masterbrain service with `POST /api/endpoints/embeddings` (available in 0.12.0), private transport/access controls, the matching Qwen provider configuration and its own usage sink integration. An older service without this endpoint degrades to keyword search; Platform never bypasses it with a direct provider call. External mode is not a shared database or a fallback to another provider.

There is no automatic bulk vector backfill when AI is re-enabled. Existing keyword-only chunks stay searchable; subsequent supported resource indexing can generate vectors. A deployment needing complete semantic coverage should separately plan a scoped, metered reindex. Do not change model/dimensions or claim backfill has completed merely by restarting the API.

Downgrading the migration refuses to set `NOT NULL` while keyword-only rows exist. Restore a verified pre-upgrade backup, or complete and verify a deliberate compatible reindex before downgrade; never delete rows or fabricate vectors just to satisfy the old schema. Follow the normal backup/restore procedure for any rollback.

## Verification

Offline API tests cover the published package endpoint, batching, disabled AI, transport failures, cancellation, malformed vectors, model/dimension consistency and usage attribution. Isolated PostgreSQL tests cover migration upgrade/downgrade, concurrent atomic replacement, punctuation-safe keyword queries, AI recovery and public/private/deleted scope isolation. They use synthetic model responses and do not claim live provider quality or availability.
