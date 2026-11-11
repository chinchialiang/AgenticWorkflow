# 02. The Six Enterprise Architectural Perspectives

This document defines the system specifications across six foundational enterprise perspectives.

---

## 1. Core Workflow & State Orchestration
- **Three-Tier State Namespace:**
  - **Domain Payload:** Core business data (e.g., `OrderRecord`, `AnalysisReport`).
  - **Workflow Control State:** Engine-level metadata (e.g., `step_count`, `retry_budget`, `requires_human_approval`, `correlation_id`).
  - **Transient Scratchpad:** Temporary agent reasoning, raw model outputs, and streaming chunks discarded or compacted on step completion.
- **Bounded Context Subgraphs:**
  - Complex domains are split into subgraphs (Modular Monolith).
  - Subgraphs expose an input/output contract to the parent graph and hide internal retry loops.
- **Pure Reducers:**
  - All state mutation logic follows pure function semantics `(CurrentState, Delta) -> NewState`.

---

## 2. Cognitive & Agent Role Subsystem
- **Decoupled Triad Pattern:**
  - **Planner Node:** Decomposes requests into a structured execution DAG (JSON schema).
  - **Worker Nodes:** Specialized execution agents with minimal, focused tool sets.
  - **Evaluator / Critic Node:** Independent validator scoring worker outputs against acceptance criteria before transition.
- **Model Gateway & Tiering:**
  - Route classification and simple extraction to fast, lightweight models (e.g., Gemini Flash / GPT-4o-mini).
  - Route planning, critique, and code generation to frontier reasoning models (e.g., Claude 3.5 Sonnet / Gemini Pro).

---

## 3. Memory & Context Management
- **Context Window Hygiene:**
  - Implement automated state compaction when message history exceeds token or turn thresholds.
  - Summarize older turns into a rolling semantic synopsis.
- **Pass-by-Reference Pattern:**
  - Large payloads (raw documents, massive SQL dumps) are stored in object storage (S3/GCS) or Vector DB.
  - Graph state only maintains URIs/pointers and metadata summaries.

---

## 4. Tool & Integration Gateway (Action Layer)
- **CQRS for Tools:**
  - **Query Tools (Read-Only):** Safe to run automatically, parallelizable, and idempotent.
  - **Command Tools (Mutating):** Require idempotency keys, authorization checks, and human governance gates.
- **Error Isolation:**
  - Catches 4xx/5xx errors, timeouts, and JSON syntax failures, wrapping them into structured `ToolResult` messages rather than crashing the workflow thread.

---

## 5. Human-in-the-Loop (HITL) & Governance
- **Stateless Asynchronous Suspension:**
  - Uses LangGraph's `interrupt()` before mutating high-consequence systems.
  - Commits snapshot to checkpointer and yields compute thread (zero compute while waiting).
  - Resumes execution upon receiving an external signal or review approval via API.
- **Time-Travel & State Mutation:**
  - Human operators can inspect paused states, edit parameters, and resume or replay from previous checkpoints.

---

## 6. Resilience, Observability & Enterprise Operations
- **Durable Checkpointer:**
  - PostgreSQL-backed checkpointer with connection pooling and row-level locking for production.
- **Safety Circuit Breakers:**
  - Hard cap on maximum node transitions (`max_iterations = 25`) to prevent runaway loops.
  - Cost budget caps per thread/tenant.
- **OpenTelemetry Tracing:**
  - `thread_id` mapped to enterprise `Correlation-ID`.
  - Every node execution forms a Span; each LLM call forms a Child Span tracking prompt, completion tokens, latency, and costs.
