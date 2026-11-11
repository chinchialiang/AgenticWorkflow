# 06. Event-Driven Listener, Dashboard Telemetry, and Decoupled Streaming

This document details the architecture of the **`GraphExecutionListener`**, the **`EventBroker`** port/adapter, and the decoupled streaming & dashboard mechanisms.

---

## 1. Architectural Motivation & Benefits

Instead of coupling cross-cutting concerns (logging, metrics, streaming, cost budgets) inside business nodes, the system adopts an **Asynchronous Event-Driven Architecture (EDA)** inspired by Camunda's `ExecutionListener` and Spring's `ApplicationEventMulticaster`.

### Core Architectural Benefits
1. **Domain Logic Purity:** Business nodes (e.g., `PlannerNode`, `CodeNode`) focus 100% on domain decisions without dependency on frontend streaming or monitoring systems.
2. **Open-Closed Principle (OCP):** Adding new telemetry, auditing, or alert integrations requires only creating and registering a new `WorkflowEventListener`—zero modifications to existing workflows.
3. **Decoupled Out-of-Band Streaming:** Streaming is freed from the HTTP Request-Response lifecycle. A background job can emit events to an event queue, allowing any frontend client to attach via SSE/WebSocket, disconnect, and reconnect without breaking graph execution.

---

## 2. Ports & Adapters Architecture

```
+----------------------------------------------------------------------------------------------------+
| Core Domain (Ports)                                                                                |
|                                                                                                    |
|   +-----------------------+            publish()             +---------------------------------+   |
|   |   GraphNode (Base)    | -------------------------------> |   WorkflowEventPublisher (Port) |   |
|   +-----------------------+                                  +----------------+----------------+   |
|                                                                               |                    |
+-------------------------------------------------------------------------------|--------------------+
| Infrastructure (Adapters)                                                     |                    |
|                                                                               v                    |
|                                                              +---------------------------------+   |
|                                                              |     EventBroker / Dispatcher    |   |
|                                                              +----------------+----------------+   |
|                                                                               |                    |
|                     +---------------------------------------------------------+                    |
|                     |                                                         |                    |
|                     v (Current: In-Process)                                    v (Future: Distributed)|
|      +------------------------------+                          +------------------------------+    |
|      |  InMemoryAsyncEventBroker    |                          |    RedisPubSubEventBroker    |    |
|      |    (asyncio.Queue)           |                          |    (or KafkaEventBroker)     |    |
|      +--------------+---------------+                          +------------------------------+    |
|                     |                                                                              |
|                     +---------------------------------------+                                      |
|                     |                   |                   |                                      |
|                     v                   v                   v                                      |
|             +---------------+   +---------------+   +---------------+                              |
|             | Dashboard     |   | NodeState     |   | Future:       |                              |
|             | Telemetry     |   | Stream        |   | Token Stream /|                              |
|             | Listener      |   | (SSE/WS)      |   | Slack Bot     |                              |
|             +---------------+   +---------------+   +---------------+                              |
+----------------------------------------------------------------------------------------------------+
```

---

## 3. The Core Event Contract (`WorkflowEvent`)

All lifecycle events across graphs and nodes share a unified schema:

```python
class WorkflowEvent(BaseModel):
    event_id: str
    event_type: WorkflowEventType  # NODE_ENTERED, NODE_STATE_CHANGED, NODE_EXITED, GRAPH_STARTED...
    thread_id: str
    trace_id: Optional[str]
    node_name: Optional[str]
    from_status: Optional[NodeStatus]
    to_status: Optional[NodeStatus]
    duration_ms: Optional[float]
    timestamp: datetime
    payload: dict[str, Any]
    message: Optional[str]
```

---

## 4. Concrete Implementations

### A. `InMemoryAsyncEventBroker`
* Implemented in [`src/agentic_workflow/gateway/event_broker.py`](../src/agentic_workflow/gateway/event_broker.py).
* Runs a non-blocking background dispatch loop (`asyncio.Queue`).
* Concurrently fans out each event to all matching subscribers with exception isolation (one failing listener cannot disrupt others or the core workflow).
* Implements the exact interface required for future drop-in replacement by `RedisPubSubEventBroker` or `KafkaEventBroker`.

### B. `NodeStateStreamListener`
* Implemented in [`src/agentic_workflow/gateway/listeners/streaming.py`](../src/agentic_workflow/gateway/listeners/streaming.py).
* Maintains a circular history buffer per `thread_id` and dispatches to active subscriber queues.
* Exposes `async def stream_events(thread_id, replay_history=True) -> AsyncGenerator[WorkflowEvent, None]`.
* Can be returned directly by FastAPI endpoints via `EventSourceResponse` (Server-Sent Events) or WebSockets.

### C. `DashboardTelemetryListener`
* Implemented in [`src/agentic_workflow/gateway/listeners/dashboard.py`](../src/agentic_workflow/gateway/listeners/dashboard.py).
* Maintains real-time operational metrics per job (`JobMetrics`):
  * Active node and status (`RUNNING`, `SUSPENDED`, `COMPLETED`, `FAILED`).
  * Total nodes executed, accumulated latency, and recent event logs.
  * Instant retrieval via `get_job_metrics(thread_id)` and `list_active_jobs()`.

---

## 5. Advanced Enterprise Applications Unlocked by This Architecture

1. **Interactive Slack/Teams HITL Bot:** Listens for `GRAPH_SUSPENDED` events and posts interactive approval cards with [Approve] / [Reject] buttons directly into channels.
2. **Watchdog / Dead-Man's Switch:** Automatically triggers alerts or failover compensation if a graph experiences no node transitions within a threshold (e.g., 120s socket hang).
3. **Shadow A/B Testing & Canary Evaluation:** Listens for `NODE_EXITED` and runs the same input against experimental candidate models (e.g., comparing Claude 3.5 Sonnet vs. Gemini 2.0 Pro) in the background without user impact.
4. **FinOps & Multi-Tenant Cost Accounting:** Aggregates token consumption in real-time, attributing costs to business units and halting runs that exceed department quotas.
5. **Time-Traveling Replay Debugger:** Enables UI scrubbing through recorded event streams to pinpoint exact agent reasoning failures.
6. **WORM Regulatory Compliance Audit:** Streams all state transitions to write-once, tamper-evident storage for financial or medical non-repudiation.
