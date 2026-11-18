# 08. LLMNode Contract & Architecture Design

本文件說明如何將現有 [cognitive.py](file:///Users/chin-chialiang/AgenticWorkflow/src/agentic_workflow/nodes/cognitive.py) 中的 `CognitiveNode` 演進為產品級的 **`BaseLLMNode` + `LLMNodeConfig`** 架構，使其同時滿足「企業級合約執行」與「視覺化 UI 雙向序列化」。

---

## 1. 設計核心：宣告式 Config 與執行期分離

目前的 `CognitiveNode` 直接接收 Python `Callable`（例如 `dod_evaluator`），無法被前端 Drag & Drop UI 編輯與儲存。產品化後必須拆分為兩層：

1. **`LLMNodeConfig`（宣告式設定，Pydantic Model）**：純資料結構，可序列化為 JSON/YAML，作為前後端交換的標準契約（Graph IR）。
2. **`BaseLLMNode(GraphNode[AgentWorkflowState])`（執行期基底類別）**：繼承 [base.py](file:///Users/chin-chialiang/AgenticWorkflow/src/agentic_workflow/nodes/base.py) 的 `GraphNode`，保留統一的生命週期狀態機（`PENDING -> RUNNING -> EVALUATING -> RETRYING -> SUCCEEDED / FAILED`）與 `EventBroker` 事件發布機制。

```
+-------------------------------------------------------------------+
|                        LLMNodeConfig (JSON/YAML)                  |
|  - model_config     - system_prompt      - user_prompt_template   |
|  - skills[]         - dod_contract       - eval_pipeline[]        |
+---------------------------------+---------------------------------+
                                  | compile / hydrate
                                  v
+-------------------------------------------------------------------+
|               BaseLLMNode(GraphNode[AgentWorkflowState])          |
|  1. PromptRenderer  -> 渲染 System Prompt 與 Task User Prompt      |
|  2. SkillResolver   -> 注入 Skill 指引並綁定 Scoped Tools / MCP   |
|  3. LLMInvoker      -> 呼叫模型（統一 Gateway Protocol）           |
|  4. EvalPipeline    -> 依 DoD 執行確定性與語意評估                |
|  5. RetryController -> 未達標時附帶 Feedback 重試或轉人工審核     |
+-------------------------------------------------------------------+
```

---

## 2. 五大核心要素詳細設計

### 2.1 System Prompt（角色與不變量）
- **職責**：定義 Agent 的長期身分、行為邊界、安全守則與輸出語氣（Invariants）。
- **設計**：支援全域變數插值（如 `{{env.company_name}}`）與版本追蹤（`prompt_version`），與單次任務指令隔離，避免角色設定被任務內容稀釋。

### 2.2 User Prompt（針對此任務的 Task Template）
- **現況補強**：目前 `CognitiveNode` 直接將整個 `state["messages"]` 丟給 LLM，缺乏針對「單一節點任務」的明確指令模板。
- **設計**：
  - **`user_prompt_template`**：使用安全的模板語法（如 Jinja2 SandboxedEnvironment）引用上游狀態與產物，例如：
    ```text
    請根據以下客戶問題與知識庫摘要，撰寫回覆草稿：
    - 客戶提問：{{ state.artifacts.user_query }}
    - 檢索結果：{{ state.artifacts.kb_snippets }}
    ```
  - **`context_policy`（上下文注入策略）**：由節點設定決定要帶入多少歷史訊息（`none` / `last_n` / `full`），避免 Token 爆炸與上下文污染。

### 2.3 Skill（能力與受限工具組）
- **設計原則**：Skill 不只是單純的 Function Calling，而是「**領域知識指引（Instructions） + 授權工具（Tools/MCP）**」的封裝單元（支援 Progressive Disclosure）。
- **`SkillSpec` 結構**：
  - `skill_id`: 唯一識別碼（如 `web_search`、`sql_readonly`）。
  - `description`: 簡短摘要，供模型與 UI 顯示。
  - `instructions`: 啟用該 Skill 時自動附加到 Prompt 的操作規範。
  - `tool_refs`: 綁定的工具名稱或 MCP Server 端點（遵循最小權限原則 Principle of Least Privilege）。

### 2.4 Definition of Done（DoD，完成定義）
將 DoD 從單純的 `output_schema` 擴展為「結構 + 語意」雙重契約：
- **`output_schema`（JSON Schema / Pydantic）**：定義輸出必須符合的資料結構與欄位型別，前端 UI 可用表單建構器產生。
- **`acceptance_criteria`（驗收標準清單）**：條列式業務規則，例如：
  - `CRIT-1`：回覆字數必須小於 300 字。
  - `CRIT-2`：不可承諾未經授權的退款金額。
  - `CRIT-3`：必須引用至少一筆 `kb_snippets` 中的來源。

### 2.5 Eval（評估管線與自癒控制）
將單一 `dod_evaluator` 升級為可組合的 **`EvalPipeline`**：

| 評估階段 | Evaluator 類型 | 實作方式 | 適用場景 |
| :--- | :--- | :--- | :--- |
| **Stage 1：確定性檢查** | `SchemaValidator` | JSON Schema / Pydantic 驗證 | 確保下游節點可安全解析輸出 |
| **Stage 1：規則斷言** | `RuleEvaluator` | Regex、長度限制、禁用詞檢查、安全沙箱 Python 表達式 | 零成本、毫秒級過濾硬性規範 |
| **Stage 2：語意裁判** | `LLMJudgeEvaluator` | 使用指定輕量模型對照 `acceptance_criteria` 打分（0.0–1.0）並生成具體 `feedback` | 驗證語氣、幻覺、邏輯完整性 |

- **執行決策（Routing & Retry）**：
  - 總分 $\ge$ `pass_threshold` 且確定性檢查全過 $\rightarrow$ 寫入 `NodeExecutionRecord` 與 `dod_evaluation` 並進入 `SUCCEEDED`。
  - 未通過且仍有重試額度 $\rightarrow$ 觸發 `NodeStatus.RETRYING`，將失敗的 Evaluator `feedback` 注入下一輪上下文自我修正。
  - 重試耗盡仍未通過 $\rightarrow$ 依據設定執行 `on_failure_policy`（`fail_workflow`、`fallback_node` 或轉為 `ExecutionStatus.WAITING_APPROVAL` 交由人工介入）。

---

## 3. 與現有系統的相容性

- **狀態相容**：`BaseLLMNode` 繼續操作 [state.py](file:///Users/chin-chialiang/AgenticWorkflow/src/agentic_workflow/domain/state.py) 定義的三層 `AgentWorkflowState`（寫入 `messages`、`artifacts`、`dod_evaluation` 與 `node_execution_history`）。
- **圖編譯相容**：透過 `WorkflowLoader` 讀取 JSON/YAML 中的 `LLMNodeConfig` 實例化為 `BaseLLMNode`，直接註冊進現有的 `WorkflowGraphBuilder`（[graph.py](file:///Users/chin-chialiang/AgenticWorkflow/src/agentic_workflow/core/graph.py)），無縫支援 `compile_langgraph()`。
- **節點擴展性**：未來可基於 `BaseLLMNode` 特化出 `SingleTurnLLMNode`（單次任務）、`ReActAgentNode`（多輪工具呼叫直到 DoD 達成）與 `JudgeRouterNode`（依 Eval 結果決定圖的分支走向）。
- **監控與安全預留**：`LLMNodeConfig` 與 `BaseLLMNode` 須預留 `guardrails`（Pre/Post PII 脫敏與注入防護）、`budget_policy`（Token/成本熔斷）、`SkillSpec.risk_level`（高風險人工審核）與 OTel `trace_id` 透傳介面，完整規範詳見 [10. Governance, Security & System Observability](10-governance-security-and-observability.md)。
