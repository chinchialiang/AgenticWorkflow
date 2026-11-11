# Agentic Workflow Platform

An enterprise-grade agentic workflow architecture inspired by Java enterprise design patterns (Spring StateMachine, BPMN, Hexagonal Architecture, EIP, and CQRS) built for LangGraph.

---

## Architectural Philosophy: *Deterministic Skeleton, Stochastic Muscle*

In this architecture, deterministic state machines govern workflow transitions, circuit breakers, security boundaries, and transactions. Stochastic Large Language Models (LLMs) operate strictly inside encapsulated nodes to provide cognitive reasoning, semantic parsing, and tool-call parameterization.

---

## Project Structure

```
AgenticWorkflow/
├── docs/                                  # Architectural design documentation
│   ├── index.md                           # Documentation Index
│   ├── 01-conceptual-mapping.md           # Java Enterprise <-> LangGraph mental model
│   ├── 02-architecture-perspectives.md    # 6 Enterprise Architecture Perspectives
│   └── 03-node-taxonomy-and-design.md     # Node Taxonomy (CognitiveNode vs ExecutionNode)
├── src/
│   └── agentic_workflow/
│       ├── domain/                        # Pure domain schemas, models, and reducers
│       │   ├── state.py                   # 3-Tier State (Domain, Control, Scratchpad)
│       │   ├── models.py                  # Value objects, DoD contracts, ToolResult
│       │   └── reducers.py                # Pure state reducers (CQRS event-sourcing style)
│       ├── nodes/                         # Discrete command handlers
│       │   ├── base.py                    # GraphNode abstract base class
│       │   ├── cognitive.py               # CognitiveNode (Prompt, Skills, DoD, Eval)
│       │   └── execution.py               # ToolExecutionNode (API & Code sandbox)
│       ├── core/                          # State machine orchestration
│       │   ├── graph.py                   # WorkflowGraphBuilder
│       │   └── routers.py                 # Content-based routers & circuit breakers
│       └── gateway/                       # Integration adapters
│           ├── llm.py                     # LLM gateway & mock providers
│           └── tools.py                   # Tool registry & permission manager
├── tests/                                 # Unit & integration tests
├── pyproject.toml
└── README.md
```

---

## Node Taxonomy

1. **`CognitiveNode` (LLM-Driven, Stochastic):**
   - **System Prompt:** Injected role, persona, and invariants.
   - **Skills:** Scoped tools bound under the principle of least privilege.
   - **DoD (Definition of Done):** Pydantic structured output contract.
   - **Eval:** Dual-stage verification (Stage 1: deterministic schema check; Stage 2: semantic acceptance evaluation) with automatic self-correction loops.

2. **`ToolExecutionNode` (Deterministic Execution):**
   - **API / Code Sandbox Runner:** Runs external I/O or sandboxed execution.
   - **Error Isolation:** Catches 4xx/5xx errors, timeouts, and syntax failures without crashing the graph.
   - **Idempotency & Timeouts:** Transaction protection on mutating operations.

---

## Quickstart & Verification

### Running Tests
```bash
python3 -m unittest discover tests/
```
