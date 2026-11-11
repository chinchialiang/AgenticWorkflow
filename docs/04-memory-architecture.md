# 04. Memory Architecture: Short-Term vs. Long-Term Memory

In an enterprise-grade agentic workflow system, state management is fundamentally divided into two operational paradigms: **Short-Term Memory** and **Long-Term Memory**.

---

## 1. Dual-Memory Paradigm Comparison

| Dimension | Short-Term Memory (Working Memory) | Long-Term Memory (Episodic & Semantic) |
| :--- | :--- | :--- |
| **Architectural Scope** | Single workflow transaction (`thread_id`) | Cross-thread, cross-session, cross-tenant |
| **LangGraph Primitive** | **`AgentWorkflowState`** via `StateGraph` | **`Store`** (`BaseStore` / `AsyncPostgresStore`) |
| **Persistence Engine** | **Checkpointer** (`PostgresSaver` / WAL) | **Relational Store + Vector DB** |
| **Hardware Analogy** | CPU Registers / RAM | Persistent Disk / Knowledge Base |
| **Lifecycle** | Transient: Created on invocation, archived on completion | Permanent: Continuously updated across sessions |
| **Core Capabilities** | Step rollback, HITL suspension, state rewind, deterministic reducers | User preferences, past lessons learned, domain entity memory |

---

## 2. Where State Resides in the Codebase

In Clean / Hexagonal Architecture, the Short-Term State represents the **Domain Aggregate Root**:

```
src/agentic_workflow/
├── domain/
│   ├── state.py          <--- Short-Term Memory Schema (AgentWorkflowState)
│   ├── models.py         <--- Value Objects (WorkflowMessage, ToolResult)
│   └── reducers.py       <--- State Reducer Logic (CQRS append/merge rules)
├── core/
│   └── graph.py          <--- Configures Checkpointer and Store
└── nodes/
    └── cognitive.py      <--- Interacts with both Short-Term State & Long-Term Store
```

### Dependency Inversion Rule
`domain/state.py` is the innermost domain layer. All nodes, routers, and gateway adapters depend inward on this state contract. The state contract depends on zero external frameworks or infrastructure code.

---

## 3. Interaction Between Short-Term and Long-Term Memory

```
                       +-----------------------------------+
                       |         Long-Term Store           |
                       | (PostgreSQL Store / Vector DB)    |
                       | Namespace: (user_id, preferences) |
                       +-----------------+-----------------+
                                         |
                       1. Read Memory    |  4. Consolidate Experience
                       (At Start of WF)  |  (After Reflection / DoD)
                                         v
+----------------------------------------------------------------------------------+
| Workflow Thread (thread_id: "tx-20261111-001")                                   |
|                                                                                  |
|   +--------------------------------------------------------------------------+   |
|   | Short-Term Working Memory (AgentWorkflowState)                           |   |
|   |                                                                          |   |
|   |  - messages: [User request, Injected preferences, Agent steps...]        |   |
|   |  - control: {step_count: 3, status: "RUNNING"}                           |   |
|   |  - scratchpad: {latest_tool_result: ...}                                 |   |
|   +-------------------------------------+------------------------------------+   |
|                                         |                                        |
|                          2. Pure Delta  |  3. Snapshot WAL                       |
|                             Updates     v                                        |
|                     +-----------------------+                                    |
|                     | PostgreSQL Checkpoint |                                    |
|                     | (Checkpointer Engine) |                                    |
|                     +-----------------------+                                    |
+----------------------------------------------------------------------------------+
```

### Lifecycle Walkthrough
1. **Memory Recall (Read):** When a workflow initializes, a bootstrap node queries the Long-Term Store by namespace (e.g., `user_id`) and injects relevant historical context into the Short-Term State (`state["messages"]`).
2. **Deterministic Step Updates:** As nodes execute, each returns a partial delta. Reducers deterministically merge updates into the Short-Term State.
3. **Step Snapshots (Checkpointer):** At every node boundary, the Checkpointer persists the current state snapshot with a monotonic `checkpoint_id`.
4. **Memory Consolidation (Write):** Upon workflow completion or major learning, an evaluator node condenses key findings and commits them back to the Long-Term Store for future workflows.
