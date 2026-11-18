# Agentic Workflow Architecture Documentation

This directory contains the foundational architectural blueprints, enterprise mental models, and node designs for the agentic workflow system built with LangGraph.

## Table of Contents

1. [01. Conceptual Mapping: Enterprise Java to LangGraph](01-conceptual-mapping.md)
   - Bridges enterprise Java concepts (Spring StateMachine, BPMN, EIP, CQRS, Sagas) with LangGraph primitives.
2. [02. The Six Enterprise Architectural Perspectives](02-architecture-perspectives.md)
   - Detailed architectural breakdown across Workflow, Cognition, Memory, Tools, HITL, and Resilience.
3. [03. Node Taxonomy and Design](03-node-taxonomy-and-design.md)
   - Specification and lifecycles of `CognitiveNode` (System Prompt, Skills, DoD, Eval) and `ExecutionNode` (API & Sandbox).
4. [04. Memory Architecture: Short-Term vs. Long-Term](04-memory-architecture.md)
   - Architectural distinction and interaction between Short-Term State (Checkpointer) and Long-Term Memory (Store).
5. [05. Node Lifecycle State Machine and Observability](05-node-lifecycle-and-observability.md)
   - Template Method Pattern, NodeStatus state transitions, structured JSON audit logs, and in-state execution history.
6. [06. Event-Driven Listener, Dashboard Telemetry, and Decoupled Streaming](06-event-listener-and-streaming.md)
   - EventBroker (Ports & Adapters), in-memory async broker, NodeStateStreamListener (SSE/WebSocket), DashboardTelemetryListener, and 6 advanced enterprise applications.
7. [07. Product Strategy, Market Positioning & Roadmap](07-product-strategy-and-roadmap.md)
   - Market differentiation ("Contract-First & Eval-Driven"), Open-Core (MIT/Apache 2.0) commercial strategy, and phased execution roadmap.
8. [08. LLMNode Contract & Architecture Design](08-llm-node-contract-design.md)
   - Decoupled `LLMNodeConfig` & `BaseLLMNode` covering System Prompt, User Prompt (Task Template), Skills, Definition of Done (DoD), and Dual-Stage Eval Pipeline.
9. [09. Open Source Commercial-Friendly Drag & Drop UI Design](09-visual-builder-ui-design.md)
   - MIT/Apache 2.0 frontend stack (`@xyflow/react`, Zustand, Tailwind/shadcn), FastAPI SSE integration with `EventBroker`, 5-Tab Node Inspector, and Eval Trace replay.
10. [10. Governance, Security & System Observability](10-governance-security-and-observability.md)
   - FinOps token/cost budget guardrails, OpenTelemetry tracing, PII redaction & guardrail hooks, SSTI/sandbox isolation, Zero-Secret Graph IR, RBAC, and immutable audit trail.
