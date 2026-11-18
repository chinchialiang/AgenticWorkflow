# Agentic Workflow Platform

An enterprise-grade agentic workflow architecture inspired by Java enterprise design patterns (Spring StateMachine, BPMN, Hexagonal Architecture, EIP, and CQRS) built for LangGraph.

---

## Architectural Philosophy: *Deterministic Skeleton, Stochastic Muscle*

In this architecture, deterministic state machines govern workflow transitions, circuit breakers, security boundaries, and transactions. Stochastic Large Language Models (LLMs) operate strictly inside encapsulated nodes to provide cognitive reasoning, semantic parsing, and tool-call parameterization.

---

## Project Structure

```
AgenticWorkflow/
├── docs/                                  # Architectural design & product documentation
│   ├── index.md                           # Documentation Index
│   ├── 01-conceptual-mapping.md           # Java Enterprise <-> LangGraph mental model
│   ├── 02-architecture-perspectives.md    # 6 Enterprise Architecture Perspectives
│   ├── 03-node-taxonomy-and-design.md     # Node Taxonomy (CognitiveNode vs ExecutionNode)
│   ├── 04-memory-architecture.md          # Short-Term State vs Long-Term Memory
│   ├── 05-node-lifecycle-and-observability.md # NodeStatus state machine & audit trail
│   ├── 06-event-listener-and-streaming.md # EventBroker & SSE/Dashboard listeners
│   ├── 07-product-strategy-and-roadmap.md # Contract-First market positioning & roadmap
│   ├── 08-llm-node-contract-design.md     # Declarative LLMNodeConfig & BaseLLMNode design
│   ├── 09-visual-builder-ui-design.md     # MIT/Apache-2.0 Drag & Drop Studio design
│   └── 10-governance-security-and-observability.md # FinOps, OTel, Guardrails & Security
├── src/
│   └── agentic_workflow/
│       ├── domain/                        # Pure domain schemas, models, and reducers
│       │   ├── state.py                   # 3-Tier State (Domain, Control, Scratchpad)
│       │   ├── models.py                  # Value objects, DoDResult, LLMUsage, ToolResult
│       │   ├── node_config.py             # Declarative LLMNodeConfig, SkillSpec, DoD, Eval
│       │   ├── workflow_config.py         # Serializable WorkflowDefinition (Graph IR)
│       │   └── reducers.py                # Pure state reducers (CQRS event-sourcing style)
│       ├── nodes/                         # Discrete command handlers
│       │   ├── base.py                    # GraphNode abstract base class
│       │   ├── cognitive.py               # CognitiveNode (Prompt, Skills, DoD, Eval)
│       │   ├── llm_node.py                # BaseLLMNode (Config-driven, Guardrails, FinOps)
│       │   └── execution.py               # ToolExecutionNode (API & Code sandbox)
│       ├── core/                          # State machine orchestration
│       │   ├── events.py                  # WorkflowEvent & EventBroker contracts
│       │   ├── graph.py                   # WorkflowGraphBuilder
│       │   ├── loader.py                  # WorkflowLoader (Graph IR -> WorkflowGraphBuilder)
│       │   └── routers.py                 # Content-based routers & circuit breakers
│       └── gateway/                       # Integration adapters
│           ├── event_broker.py            # InMemoryAsyncEventBroker
│           ├── listeners/                 # Streaming & Dashboard telemetry listeners
│           ├── llm.py                     # LLM gateway, usage normalization & mocks
│           └── tools.py                   # Tool registry & permission manager
├── tests/                                 # Unit & integration tests
├── pyproject.toml
└── README.md
```

---

## Node Taxonomy

1. **`BaseLLMNode` & `LLMNodeConfig` (Declarative, Governance-Ready LLM Node):**
   - **System Prompt:** Role definition, invariants, and active skill instructions.
   - **Task User Prompt (`user_prompt_template`):** SSTI-safe dot-path state interpolation (`{{ state.artifacts.xxx }}`) with configurable `ContextPolicy`.
   - **Scoped Skills (`SkillSpec`):** Domain instructions, whitelisted `tool_refs`, `risk_level` / `requires_approval` HITL gating, and zero-secret `secret_refs` URIs (`vault://`, `env://`, `kms://`).
   - **Definition of Done (`DoDContract`):** Structural JSON Schema / Pydantic contract + semantic acceptance criteria.
   - **Dual-Stage Eval Pipeline (`EvalConfig`):** Deterministic checks (`schema`, `regex`, `length`, `forbidden_terms`) + semantic `llm_judge`, with automatic self-correction loops (`NodeStatus.RETRYING`) and `FailurePolicy` routing.
   - **Governance & FinOps:** Pre/Post-LLM `GuardrailConfig` (prompt-injection check & PII redaction) and `BudgetPolicy` (`max_tokens`, `max_cost_usd`, `timeout_seconds`).

2. **`CognitiveNode` (Code-First LLM Node):**
   - Lightweight programmatic node with `system_prompt`, `skills`, `output_schema`, and callable `dod_evaluator`.

3. **`ToolExecutionNode` (Deterministic Execution):**
   - **API / Code Sandbox Runner:** Runs external I/O or sandboxed execution.
   - **Error Isolation:** Catches 4xx/5xx errors, timeouts, and syntax failures without crashing the graph.
   - **Idempotency & Timeouts:** Transaction protection on mutating operations.

---

## Declarative Workflow Loading (Graph IR)

Workflows can be serialized as JSON/YAML using `WorkflowDefinition` (nodes, edges, conditional routes, and visual canvas `ui_metadata`) and compiled into an executable `WorkflowGraphBuilder` via `WorkflowLoader`:

```python
from agentic_workflow.core import WorkflowLoader
from agentic_workflow.gateway.llm import MockLLMInvoker

loader = WorkflowLoader(llm_invoker=MockLLMInvoker(canned_response='{"reply": "ok"}'))
builder = loader.load(workflow_definition_json)
```

---

## Quickstart & Verification

### Running Tests
```bash
python -m unittest discover -s tests -v
```
