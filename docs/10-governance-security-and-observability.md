# 10. Governance, Security & System Observability

本文件定義系統在邁向企業級商業產品時，必須預先內嵌於執行引擎（`BaseLLMNode`、`EventBroker`、`LLMInvokerProtocol`）與前端閘道（FastAPI）的**安全控管（Security）、合規治理（Governance）與系統監控（Observability）**架構。

---

## 1. 系統監控與可觀測性（System Monitoring & Observability）

### 1.1 FinOps：Token 與成本追蹤及預算熔斷
- **標準化回傳契約**：`LLMInvokerProtocol` 必須回傳結構化的用量中繼資料（`prompt_tokens`、`completion_tokens`、`cached_tokens`、`cost_usd`、`model_id`），並寫入 `NodeExecutionRecord.metadata`。
- **預算熔斷器（Budget Guardrails）**：在 `LLMNodeConfig` 與 `WorkflowDefinition` 層級設定 `max_budget_usd` 與 `max_tokens`。當 `RETRYING` 自癒迴圈或長流程累積消耗逼近上限時，引擎強制中止並發布告警事件，防止失控費用。

### 1.2 分散式追蹤（OpenTelemetry 相容）
- **Trace 上下文貫穿**：透過 `AgentWorkflowState` 或 `RunnableConfig` 傳遞 `trace_id` 與 `parent_span_id`。
- **Span 階層樹**：`Workflow Run -> BaseLLMNode -> Pre-Guardrail -> LLM Call -> Skill/Tool -> Eval Pipeline -> Post-Guardrail`，可無縫匯出至 Grafana Tempo、Datadog、Langfuse 或 Arize。

### 1.3 Eval 品質與系統健康 SLI / SLO
透過訂閱 `EventBroker` 事件，衍生即時監控指標：
- **品質指標**：首次通過率（First-Pass DoD Rate）、平均自我修正次數（Avg Retries）、Eval 分數漂移（Score Drift）。
- **效能與韌性指標**：P95 節點延遲、LLM Gateway 429 限流率、Circuit Breaker 開啟次數與 Fallback Model 切換率。

---

## 2. 安全控管與治理（Governance & Security）

### 2.1 輸入輸出防護閘（Guardrail Hooks & PII 脫敏）
`BaseLLMNode` 執行生命週期內建可插拔的雙向防護鉤子：
- **Pre-LLM Guardrail**：偵測 Prompt Injection / Jailbreak，並對輸入中的敏感個資（PII、信用卡號、憑證）進行 **Redaction / Masking（先脫敏再送外部模型）**。
- **Post-LLM Guardrail**：檢查模型輸出是否洩漏 System Prompt 或內部敏感資訊；**所有寫入 `EventBroker`、SSE 串流與 `NodeExecutionRecord` 的資料皆須經過脫敏處理**。

### 2.2 模板注入防護（SSTI）與規則沙箱
- **安全模板渲染**：`user_prompt_template` 必須使用受限沙箱引擎（如 `jinja2.sandbox.SandboxedEnvironment`），嚴禁存取物件私有屬性或執行任意 Python 方法。
- **Eval 規則隔離**：Stage 1 Deterministic Eval 若允許自訂邏輯，僅可使用受限表達式（如 CEL / 受限 AST）或容器化沙箱（Docker / gVisor），禁止在主進程直接呼叫 `eval()` / `exec()`。

### 2.3 Skill 最小權限與高風險人工審批（HITL Gate）
- **雙重白名單校驗**：模型發起 Tool Call 時，Gateway 必須在執行前再次驗證該工具確實存在於該節點 `LLMNodeConfig.skills` 授權清單中，不可僅依賴 Prompt 約束。
- **風險分級與簽核**：`SkillSpec` 須宣告 `risk_level`（`read_only` / `write` / `critical`）。當 `critical` 動作（如寫入核心資料庫、發送外部郵件、金流操作）被觸發時，引擎強制轉入 `ExecutionStatus.WAITING_APPROVAL`，等待授權人員審核通過後才繼續。

### 2.4 憑證隔離（Zero-Secret in Graph IR）
- **嚴禁明文憑證**：API Key、資料庫連線字串與 OAuth Token 絕不可出現於前端匯出的 Graph JSON 或 `AgentWorkflowState` 中。
- **動態引用解析**：節點設定僅保存 `secret_ref`（例如 `vault://crm/api_key`），由後端執行引擎在呼叫工具或 LLM 的瞬間從 Secret Manager / KMS 動態注入。

### 2.5 多租戶隔離、RBAC 與不可變審計（Audit Trail）
- **多租戶邊界**：`tenant_id` 與 `actor_id` 必須貫穿 API 請求、State Checkpointer 與 `EventBroker` 訂閱過濾器，確保租戶間的事件流與執行歷史完全隔離。
- **資源上限治理**：FastAPI `/workflows/run` 驗證層強制套用系統級上限（`max_steps`、`max_self_retries`、`timeout_seconds`），防止惡意迴圈拓撲造成 DoS。
- **Immutable Audit Log**：完整記錄「誰在何時修改了哪個版本的 Prompt/DoD」、「誰核准或拒絕了高風險 Skill 執行」，滿足企業合規稽核要求。

---

## 3. Phase 1 介面預留檢核表（Pre-Flight Checklist）

為避免未來重構，Phase 1 實作即須預留以下欄位與介面：
- [ ] `LLMNodeConfig` 預留 `guardrails`、`budget_policy`、`timeout_seconds` 欄位。
- [ ] `SkillSpec` 預留 `risk_level`、`requires_approval`、`secret_refs` 欄位。
- [ ] `LLMInvokerProtocol` 回傳標準化包含 `usage`（Tokens / Cost）與 `model_id`。
- [ ] `AgentWorkflowState` / `WorkflowEvent` 預留 `tenant_id` 與 `trace_id` 欄位。
