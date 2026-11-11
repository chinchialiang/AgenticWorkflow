# 01. Conceptual Mapping: Enterprise Java to LangGraph

This document establishes the conceptual bridge between Enterprise Java architectural patterns and LangGraph runtime concepts.

---

## 1. Enterprise Java vs. LangGraph Mental Model

LangGraph is fundamentally an asynchronous, stateful, message-driven finite state machine (FSM). For a Java architect, it maps cleanly to established enterprise patterns:

| Enterprise Java / Architecture Concept | LangGraph Concept | Architectural Role |
| :--- | :--- | :--- |
| **State Machine Context / Aggregate Root** | **Graph State** (`TypedDict` / Pydantic `BaseModel`) | Canonical, immutable workflow state. |
| **CQRS Event Reducer / Append Log** | **Field Reducers** (`Annotated[list, add]`, custom reducers) | Dictates how node outputs mutate the aggregate state. |
| **Command Handler / Stateless Spring Service** | **Node** | Pure execution unit: `(State) -> StateDelta`. |
| **Content-Based Router (EIP / Camel) / Guard** | **Conditional Edge** | Evaluates state to determine the next transition path. |
| **Saga Orchestrator / Compensation Flow** | **Graph Topology + Fallback Edges** | Sequences tasks, retries, and compensation routes on failures. |
| **Event Store / Write-Ahead Log (WAL)** | **Checkpointer** (`PostgresSaver`, `MemorySaver`) | Snapshot persistence per step, crash recovery, and time travel. |
| **BPMN User Task / Async Callback** | **Human-in-the-Loop (`interrupt`)** | Suspends execution thread at an explicit boundary until external approval is received. |
| **Bounded Context / Subsystem** | **Compiled Subgraph** | Encapsulated, reusable state machine embedded as a single node in a parent graph. |

---

## 2. Core Architectural Principles

1. **Deterministic Skeleton, Stochastic Muscle:**
   - The workflow topology (transitions, safety gates, audit checkpoints, error handling) is governed by deterministic code.
   - The LLM is only invoked inside nodes for unstructured interpretation, synthesis, or tool-parameter selection.
2. **Immutable Aggregate State:**
   - Nodes do not mutate external state directly.
   - Nodes receive a read-only snapshot of the state and return an incremental delta dictionary.
3. **Stateless Node Execution:**
   - Node functions and classes remain stateless across invocations; all conversation and execution state resides in the Checkpointer.
