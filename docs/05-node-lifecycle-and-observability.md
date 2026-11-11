# 05. Node Lifecycle State Machine and Observability

This document details the node lifecycle specification, the Template Method Pattern, and structured event logging across state transitions.

---

## 1. Node Micro-Lifecycle FSM

Each node execution instance transitions through discrete lifecycle states:

```
                  +-------------------+
                  |      PENDING      |
                  +---------+---------+
                            |
                            v
                  +-------------------+
           +----> |      RUNNING      |
           |      +----+----+----+----+
           |           |    |    |
  [Retry Loop]         |    |    +-----------------------------+
           |           |    |                                  |
           |           |    v (CognitiveNode only)             v (ToolNode / API)
           |           |  +--------------------+         +-------------------+
           |           |  |     EVALUATING     |         | WAITING_EXTERNAL  |
           |           |  +----+----------+----+         +---------+---------+
           |           |       |          |                        |
           +-----------+-------+          |                        |
           |  [DoD Failed / Retry]        |                        |
           |                              v                        v
   +-------+-------+             +-----------------+     +-------------------+
   |    FAILED     |             |    SUCCEEDED    |     |     SUCCEEDED     |
   +---------------+             +-----------------+     +-------------------+
```

### State Definitions
* **`PENDING`:** Node is scheduled by the graph engine.
* **`RUNNING`:** Execution has started. Timer starts and enter log is emitted.
* **`EVALUATING`:** LLM response is undergoing Stage 1 schema parsing or Stage 2 semantic DoD evaluation.
* **`WAITING_EXTERNAL`:** Node is waiting for external I/O (REST API, database, or sandbox container).
* **`RETRYING`:** Self-healing loop active due to evaluation failure or transient error.
* **`SUCCEEDED`:** Execution completed successfully; state delta is generated.
* **`FAILED`:** Retries exhausted or unrecoverable exception encountered.

---

## 2. Template Method Pattern (`GraphNode`)

To eliminate boilerplate and ensure consistent logging across all nodes, `GraphNode` enforces the **Template Method Pattern**:

1. Subclasses implement only `_on_execute(state) -> dict[str, Any]`.
2. The base `__call__` method automatically handles:
   - Emitting the `ENTER` event log (`PENDING` $\rightarrow$ `RUNNING`).
   - Starting precision timers (`time.perf_counter()`).
   - Catching unhandled exceptions and translating them into `FAILED` records.
   - Emitting the `EXIT` event log (`SUCCEEDED` or `FAILED`) with exact execution latency.
   - Recording a `NodeExecutionRecord` into `state["node_execution_history"]`.

---

## 3. Structured Event Logging Format

State transitions emit structured JSON logs compatible with enterprise log aggregators (ELK, CloudWatch, Datadog):

```json
{
  "event": "NODE_STATE_CHANGED",
  "node_name": "planner_node",
  "from_status": "EVALUATING",
  "to_status": "RETRYING",
  "attempt": 2,
  "max_retries": 2,
  "reasons": ["Need at least 2 steps"],
  "message": "Node 'planner_node' retrying with evaluation feedback."
}
```

---

## 4. State Audit Trail (`NodeExecutionRecord`)

Every node execution appends a record to the workflow control state:

```python
class NodeExecutionRecord(BaseModel):
    node_name: str
    status: NodeStatus
    duration_ms: float
    started_at: datetime
    completed_at: datetime
    attempt: int = 1
    error_message: Optional[str] = None
    metadata: dict[str, Any]
```

This guarantees complete traceability during human audits, post-mortems, and debugging.
