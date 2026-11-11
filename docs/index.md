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
