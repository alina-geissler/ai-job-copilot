# 14 — Challenges and Engineering Decisions

> **Related documents:** [02-architecture.md](02-architecture.md) | [09-ai-analysis.md](09-ai-analysis.md) | [11-engineering-practices.md](11-engineering-practices.md)

---

## Decision 1: Server-Rendered HTML vs. Single-Page Application (SPA)

**Decision:** Use FastAPI + Jinja2 for server-rendered HTML instead of building a React/Vue SPA with a JSON API.

**Rationale:**
- Faster development pace: no separate frontend project, no API contract negotiation, no JSON serialisation layer
- Single codebase: Python handles both logic and rendering
- HTMX provides 80% of SPA-like interactivity (polling, partial swaps) without a JavaScript build pipeline
- Simpler deployment: one process serves everything

**Trade-offs:**
| Advantage | Disadvantage |
|---|---|
| No build system or bundler needed | Full page re-renders for most navigations |
| German UI strings directly in templates | No component reusability across pages |
| FastAPI DI works seamlessly for template context | Harder to add a mobile app or third-party integrations later |
| Progressive enhancement with HTMX | Complex state (cover letter editor) requires significant inline JS |

**Alternative considered:** React frontend + FastAPI JSON API. Rejected because it would double the development surface area for a solo developer/prototype.

---

## Decision 2: Monolithic Architecture vs. Microservices

**Decision:** Modular monolith — all features in a single FastAPI process.

**Rationale:**
- A university capstone project does not need the operational complexity of microservices
- Microservices introduce: inter-service communication overhead, distributed tracing, service discovery, network partitions
- The modular monolith achieves clean separation of concerns through layered architecture without network boundaries

**Trade-offs:**
| Advantage | Disadvantage |
|---|---|
| Simple deployment (one process) | LLM-intensive background tasks compete for the same process resources as web requests |
| Easy to refactor across module boundaries | Scaling requires careful statelessness discipline |
| No inter-service serialization | A crash affects all features simultaneously |

**Future path:** The service layer is designed so that extracting individual services (e.g., a dedicated "cover-letter-generator" service) is feasible without changing the CRUD or model layers.

---

## Decision 3: OpenAI Responses API vs. Chat Completions API

**Decision:** Use the newer OpenAI **Responses API** with structured output for job normalization and cover letter generation, rather than the classic `chat.completions.create` API.

**Rationale:**
- Structured output (`text.format` with a Pydantic schema) guarantees parseable, typed output — no manual JSON extraction or retry loops for malformed responses
- `gpt-5-mini` is a reasoning model — the Responses API provides native reasoning support (`reasoning` parameter)
- Eliminates the need for complex prompt instructions to force JSON output

**Trade-offs:**
| Advantage | Disadvantage |
|---|---|
| Type-safe, validated LLM output | Newer API; less community documentation than chat completions |
| No post-processing of LLM text | `strict=False` required for complex Pydantic schemas with `anyOf` (unions) |
| Reasoning level configurable per call | |

---

## Decision 4: OpenAI (Cloud) vs. Ollama (Local) for LLM

**Decision:** Use OpenAI API (`gpt-5-mini`) as the primary LLM provider for cover letter generation and job normalization; use OpenRouter/Ollama for CV extraction.

**Rationale:**
- OpenAI's `gpt-5-mini` produces higher-quality structured output and cover letter prose than smaller local models
- For CV extraction (simpler text restructuring), `qwen2.5-7b` on OpenRouter/Ollama is sufficient and cheaper
- Ollama is available in Docker Compose for local experimentation but not yet the default path for CV extraction
- Data privacy concern partially addressed by using OpenRouter for CV extraction (qwen2.5 is open-source; OpenRouter's data retention differs from OpenAI's)

**Trade-offs:**
| Advantage | Disadvantage |
|---|---|
| Best output quality for cover letters | API cost per generation |
| No local GPU required | OpenAI service dependency for critical feature |
| OpenRouter bridges local/cloud gap | OpenRouter adds another service dependency |

---

## Decision 5: Three-Call Pipeline for Cover Letter Generation

**Decision:** Split cover letter generation into three sequential LLM calls (Analysis → Writing → Verification) instead of one large prompt.

**Rationale:**
- A single-call approach asking the LLM to simultaneously analyse fit, write the letter, and check compliance produces lower-quality output (the model is trying to do too much at once)
- Decomposition matches how a human expert would approach the task: research → write → review
- The fit_plan from Call A is explicit, inspectable, and can be re-used in future (e.g., for interview preparation)
- Call C is a separate compliance audit — isolating it means the writing call is not constrained by having to self-audit simultaneously

**Trade-offs:**
| Advantage | Disadvantage |
|---|---|
| Higher output quality (focused prompts) | 3–5x the LLM cost of a single-call approach |
| Intermediate outputs (fit_plan) are inspectable | 15–60s generation time (sequential blocking) |
| Compliance verification is independent | Call C may miss violations (acknowledged limitation) |

---

## Decision 6: JSONB for LLM Output Storage

**Decision:** Store `normalized_data`, `content`, and `layout_settings` as `JSONB` columns rather than normalised relational fields.

**Rationale:**
- LLM output schemas evolve frequently during development — a relational schema would require migrations for every field addition
- JSONB in PostgreSQL is indexed, queryable, and supports partial updates
- Cover letter `content` has a fixed structure (6 fields) but the field types and nesting may evolve
- `layout_settings` is a pure configuration object with no relational meaning

**Trade-offs:**
| Advantage | Disadvantage |
|---|---|
| No migration needed when LLM schema evolves | Cannot enforce field-level NOT NULL or FK constraints on JSONB contents |
| Flexible storage for evolving AI outputs | Harder to query individual fields (though currently not needed) |
| Aligns with JSON-native API responses | JSONB serialization adds slight overhead vs. columns |

---

## Decision 7: Privacy-First LLM Design

**Decision:** Never send private contact data (name, email, phone, address, signature) to the LLM.

**Rationale:**
- Data protection principle: minimum necessary disclosure to third parties
- Reduces GDPR exposure — OpenAI is a US-based data processor; PII minimisation reduces risk
- LLMs do not need personal contact data to write good cover letter body text; they only need professional history and skills
- Injecting contact data post-generation is architecturally cleaner and avoids hallucination (the LLM cannot make up wrong phone numbers)

**Implementation:** `_build_profile_dict()` in `cover_letter_service.py` explicitly constructs a filtered dict; private fields injected into `content` after all LLM calls complete.

---

## Decision 8: Versioned Prompts

**Decision:** Maintain a `VERSIONS` dictionary in each prompt module so that new prompt versions can be introduced without breaking existing code.

**Rationale:**
- Prompt quality is iterative; a v2 prompt may produce better output but needs testing before replacing v1 everywhere
- Old versions serve as a baseline for evaluating improvements against eval logs
- Prompt text is code — it should be version-controlled and reviewable

**Limitation:** Currently there is no automated A/B testing framework or statistical comparison tooling. Prompt improvement is manual and judgment-based.

---

## Challenge: Cover Letter Editor Complexity

**Problem:** The cover letter editor needs to support: (1) live A4 preview, (2) inline text editing without breaking the document layout, (3) design control changes without losing user edits, (4) unsaved-changes detection, (5) PDF export with current settings.

**Solution:** A combination of:
- HTMX live preview (server re-renders the document fragment)
- `contentEditable` fields with `data-field` attribute hooks
- `_savedState` snapshot before HTMX swaps, restored after (prevents preview updates from overwriting edits)
- Navigation guard modal via `<dialog>` element
- JavaScript PDF export orchestration (flush to DB → presigned URL → iframe download)

**Trade-off:** This complexity is concentrated in a single 1,250-line template file (`templates/cover_letter_editor.html`). A React/Vue component would be easier to maintain but would require a full SPA migration.

---

## Challenge: Background Task Reliability

**Problem:** FastAPI `BackgroundTasks` are ephemeral — a server restart drops in-flight tasks, leaving cover letters in `PENDING` state permanently.

**Current mitigation:** Status columns (`generation_status`) track state; `PENDING` records that are very old could be surfaced to the user with a "retry" option.

**Recommended solution:** Replace `BackgroundTasks` with Celery + Redis for durable, restartable task execution. This would also enable task progress reporting beyond a binary PENDING/COMPLETED status.
