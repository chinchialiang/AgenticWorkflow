# 03. Node Taxonomy and Design

This document details the typed node architecture: `CognitiveNode` (LLM-driven) and `ExecutionNode` (Deterministic tool/code runner).

---

## 1. Node Taxonomy Overview

```
                        +----------------------------+
                        |      GraphNode (Base)      |
                        |      (State) -> Delta      |
                        +--------------+-------------+
                                       |
                +----------------------+----------------------+
                |                                             |
                v                                             v
  +---------------------------+                 +---------------------------+
  |       CognitiveNode       |                 |       ExecutionNode       |
  | (LLM Reasoning & Eval)    |                 | (API & Sandbox Runner)    |
  +---------------------------+                 +---------------------------+
  | - System Prompt           |                 | - API Outbound Adapter    |
  | - Scoped Skills (Tools)   |                 | - Code Execution Sandbox  |
  | - Definition of Done (DoD)|                 | - Idempotency & Retries   |
  | - Dual-Stage Eval         |                 | - Error Isolation         |
  +---------------------------+                 +---------------------------+
```

---

## 2. CognitiveNode Specification

A `CognitiveNode` encapsulates non-deterministic reasoning inside an enterprise contract:

### A. Components
1. **System Prompt:**
   - Templated persona and strict role constraints injected with current state context.
2. **Skills:**
   - Scoped set of tools/functions explicitly granted to this node (Principle of Least Privilege).
3. **Definition of Done (DoD):**
   - Formal schema contract (e.g., Pydantic model) and required acceptance criteria.
4. **Eval (Evaluation Guard):**
   - **Stage 1 (Deterministic):** Schema validation, type checking, required field enforcement.
   - **Stage 2 (Semantic):** LLM-as-a-judge or assertion evaluation verifying whether the generated response meets the DoD criteria.

### B. Self-Correction Lifecycle
- If `Eval` passes $\rightarrow$ Returns state delta.
- If `Eval` fails and retries remain $\rightarrow$ Appends evaluation feedback to the internal prompt and retries.
- If retries exhausted $\rightarrow$ Flags error in workflow control state and transitions to escalation/fallback edge.

---

## 3. ExecutionNode Specification

An `ExecutionNode` contains zero LLM inference. It is a deterministic command handler.

### A. Components
1. **Target Types:**
   - **API Outbound Adapter:** REST/gRPC/DB queries with timeouts and authentication propagation.
   - **Code Execution Sandbox:** Isolated runtime (Docker, gVisor, or subprocess) for executing Python, SQL, or shell scripts.
2. **Resilience & Governance:**
   - **Circuit Breakers & Timeouts:** Guarantees that hanging external dependencies do not stall the graph.
   - **Idempotency Keys:** Protects against duplicate mutations during retries.
   - **Error Isolation:** Translates raw runtime exceptions into standardized `ToolResult` objects:
     ```python
     class ToolResult(BaseModel):
         status: Literal["SUCCESS", "FAILED"]
         output: Any = None
         error_message: str | None = None
         execution_time_ms: float
     ```
