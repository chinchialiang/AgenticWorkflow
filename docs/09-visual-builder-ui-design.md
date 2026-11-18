# 09. Open Source Commercial-Friendly Drag & Drop UI Design

本文件定義視覺化 Workflow Studio 的技術選型、授權合規策略、前後端即時通訊架構，以及針對 `LLMNode` 五大要素的介面設計。

---

## 1. 開源與商業授權策略（License Compliance）

為確保開源版本可被企業客戶與商業專案自由使用、二開與部署，前端技術棧嚴格限制僅採用 **MIT / Apache 2.0 / BSD** 授權套件，完全避開 GPL / AGPL 或需要強制付費授權的核心元件：

| 層級 | 選型方案 | 授權條款 | 選用理由 |
| :--- | :--- | :--- | :--- |
| **前端框架** | React 19 + TypeScript + Vite | MIT | 生態系最成熟、型別安全、建置速度快。 |
| **畫布引擎** | **`@xyflow/react` (React Flow)** | **MIT** | 業界標準節點畫布（核心開源免費商用；自建客製化 Node/Edge 元件即可，不依賴付費 Pro 範本）。 |
| **狀態管理** | Zustand | MIT | 輕量、支援細粒度訂閱，適合高頻更新畫布節點與 SSE 執行狀態。 |
| **UI 元件庫** | Tailwind CSS + shadcn/ui (Radix) | MIT | 高度可客製化、無執行期綁定、極佳的無障礙與深色模式支援。 |
| **編輯器元件** | Monaco Editor / CodeMirror 6 | MIT | 用於編輯 System/User Prompt（支援 `{{變數}}` 高亮）、JSON Schema 與規則表達式。 |

---

## 2. 系統架構與即時觀測橋接

前端 UI 不直接執行模型推理，而是透過 **Graph IR（JSON）** 與後端 FastAPI 溝通，並直接消費現有 [event_broker.py](file:///Users/chin-chialiang/AgenticWorkflow/src/agentic_workflow/gateway/event_broker.py) 發布的即時事件。

```
+-----------------------------------------------------------------------+
|                    Browser (React + @xyflow/react)                    |
|  [Canvas Nodes] <--- Zustand Store <--- SSE / WebSocket Client        |
|        |                                        ^                     |
|        | Export Graph IR (JSON)                 | WorkflowEvent       |
|        v                                        | (RUNNING/EVAL/RETRY)|
+--------+----------------------------------------+---------------------+
         | HTTP POST /workflows/run               | GET /events/stream
         v                                        |
+--------+----------------------------------------+---------------------+
|                     Backend Gateway (FastAPI)                         |
|  WorkflowLoader -> WorkflowGraphBuilder -> Compiled Graph             |
|                                               |                       |
|                                         EventBroker                   |
+-----------------------------------------------------------------------+
```

### 關鍵 API 端點規劃
1. `POST /api/v1/workflows/validate`：驗證 Graph 拓撲（無孤立節點、無非預期死鎖迴圈、強制檢查 `max_steps` / `max_self_retries` 資源上限）與各 `LLMNodeConfig` Schema。
2. `POST /api/v1/workflows/run`：將 Graph IR 編譯並啟動執行，回傳 `thread_id`（強制綁定 `tenant_id` 與 `trace_id`）。
3. `POST /api/v1/nodes/test`：**單節點 Playground**，傳入模擬 `state` 測試單一 `LLMNode` 的 Prompt、Skill 與 Eval 表現。
4. `GET /api/v1/workflows/{thread_id}/events`：透過 SSE（Server-Sent Events）串流 `WorkflowEvent`，驅動畫布即時亮燈（資料須經租戶權限驗證與 PII 脫敏，詳見 [10. Governance, Security & System Observability](10-governance-security-and-observability.md)）。
5. **憑證安全規範**：前端畫布與匯出的 Graph IR 僅允許存放 `secret_ref`（如 `vault://...`），嚴禁在瀏覽器端保存或回傳明文 API Key。

---

## 3. UI 核心介面與差異化設計

### 3.1 畫布上的 `LLMNode` 視覺卡片
不同於傳統只顯示節點名稱的方塊，每個 `LLMNode` 卡片直接呈現工程契約摘要：
- **頂部狀態列**：依據 `NodeStatus` 即時變色與動畫提示（`RUNNING` 藍燈脈動、`EVALUATING` 紫燈驗收中、`RETRYING` 黃燈顯示 `Attempt 2/3`、`SUCCEEDED` 綠燈、`FAILED` 紅燈）。
- **摘要徽章（Badges）**：顯示綁定的 Model、掛載的 Skill 數量、DoD Schema 狀態、以及最近一次執行的 **Eval 分數（如 `0.92`）與耗時（`ms`）**。
- **多出口連接埠（Handles）**：`on_success`（綠線）與 `on_eval_failed`（紅線，可接往人工審核或 Fallback 節點）。

### 3.2 右側 5-Tab 節點合約檢查器（Node Inspector）
點擊畫布上的 `LLMNode` 後，右側展開專為設計需求打造的五個設定分頁：

1. **System & Model**：選擇 LLM Provider/Model、Temperature、Max Tokens，並編輯 `system_prompt`。
2. **Task (User Prompt)**：編輯 `user_prompt_template`，提供「插入上游變數」快捷選單（自動列出前驅節點產出的 `state.artifacts` 欄位）與 `context_policy` 設定。
3. **Skills**：從全域 Skill Registry 勾選或拖入此節點可使用的 Skills / MCP Tools，並檢視該 Skill 會注入的指令片段。
4. **DoD (Definition of Done)**：
   - 視覺化 JSON Schema 欄位編輯器（欄位名稱、型別、必填、描述）。
   - 條列式「語意驗收條件（Acceptance Criteria）」編輯器。
5. **Eval & Retry**：
   - 組合 Stage 1（Schema / Regex / 規則）與 Stage 2（LLM-as-a-Judge 模型與評分標準）。
   - 設定 `pass_threshold`、`max_self_retries` 與失敗處理策略，並附帶 **「Run Node Test」** 即時試跑按鈕。

### 3.3 底部執行追蹤與重播面板（Execution & Eval Trace）
- 顯示每個節點的 `NodeExecutionRecord` 時間軸。
- 展開任一節點的 `RETRYING` 紀錄，可清楚看到：**Attempt 1 輸出 $\rightarrow$ Eval 扣分原因（Feedback） $\rightarrow$ Attempt 2 修正後輸出**，讓開發者與業務人員能直觀理解 Agent 自我修正的過程。
