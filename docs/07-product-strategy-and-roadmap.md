# 07. Product Strategy, Market Positioning & Roadmap

本文件定義從現有核心架構（`GraphNode`、`WorkflowGraphBuilder`、`EventBroker`）演進為**可商業化完整產品**的市場定位、開源授權策略與分階段開發路線圖。

---

## 1. 市場現況與競爭定位

目前的 AI Workflow / Agentic 平台主要分為兩大陣營：

1. **通用自動化與低代碼派（n8n、Dify、Flowise、LangFlow）**
   - **優勢**：上手門檻低、連接器豐富。
   - **痛點**：缺乏對「節點輸出品質」的工程化保證。Prompt 串接完能跑即可，進入生產環境常因 LLM 幻覺、格式飄移或缺乏驗證而靜默失敗。
2. **純開發者框架派（LangGraph、CrewAI、AutoGen）**
   - **優勢**：狀態機與控制流極度精準。
   - **痛點**：缺乏對產品經理、領域專家友善的視覺化介面；Evaluation 多半被當作「離線事後測試」，而非「執行期契約」。

### 核心產品定位（Market Wedge）

> **「Contract-First & Eval-Driven 的企業級 Agentic Workflow 平台」**

透過兩大差異化支柱切入市場：
1. **Node 即合約（Contract-First LLMNode）**：強制每個與 LLM 溝通的節點具備 `System Prompt`、`User Prompt (Task)`、`Skill`、`Definition of Done (DoD)` 與 `Eval`。將品質驗證直接內嵌進 Runtime（自我修正迴圈 + 可觀測評分），解決企業導入 AI 最痛的「不可靠、難驗收、難除錯」問題。
2. **純淨可商用開源（MIT / Apache 2.0）**：避開 AGPL 或限制性商業授權陷阱，讓企業內部團隊、SI 系統整合商與新創公司能安心採用與二開，快速建立開發者社群。

---

## 2. 商業模式規劃（Open-Core）

| 層級 | 授權方式 | 包含能力 |
| :--- | :--- | :--- |
| **Core & OSS Studio** | **Apache 2.0 / MIT** | `GraphNode` / `BaseLLMNode` 執行引擎、宣告式 Graph IR（JSON/YAML）、單機版 Drag & Drop UI（`@xyflow/react`）、基礎 Evaluators、SSE 即時狀態監控。 |
| **Team / Enterprise** | **商業授權 / 託管 SaaS** | 多租戶與 RBAC 權限控管、SSO（SAML/OIDC）、完整 Audit Log、**Eval Dataset 回歸測試中心**（失敗節點一鍵轉測試案例）、Prompt/Skill 版本管理與 A/B 流量切換。 |

---

## 3. 分階段開發路線圖（Phased Roadmap）

### Phase 1：確立 `LLMNode` 宣告式契約（Backend Core）
- **目標**：讓 Workflow 與 LLM 節點可完全透過 JSON/YAML 宣告並執行，不依賴硬編碼 Python callable。
- **關鍵交付**：
  - 定義 `LLMNodeConfig`、`SkillSpec`、`DoDContract`、`EvalConfig`（Pydantic Models）。
  - 實作 `BaseLLMNode`（支援 `user_prompt` 模板渲染、Skill 注入、Dual-Stage Eval Pipeline 與自癒重試）。
  - 實作 `WorkflowLoader`，將標準化的 Graph IR JSON 編譯為 `WorkflowGraphBuilder` 執行圖。

### Phase 2：MVP 視覺化畫布與即時監控（OSS UI + API）
- **目標**：推出開源可商用的 Drag & Drop Studio，並與現有 `EventBroker` 串接實現「即時執行觀測」。
- **關鍵交付**：
  - FastAPI 執行閘道（`/workflows/validate`、`/workflows/run`、`/events/stream` SSE）。
  - React + `@xyflow/react` + Zustand 畫布，內建 **5-Tab Node 合約檢查器**。
  - 2–3 個示範範本（如：「自動客服回覆 + 合規 Eval 守門員」、「文件結構化抽取 + Schema 強制驗證」）。

### Phase 3：Eval 驅動成長與企業級擴展（Open-Core Commercialization）
- **目標**：建立「執行失敗 $\rightarrow$ 沉澱為 Eval Dataset $\rightarrow$ 優化 Prompt/Skill」的資料飛輪。
- **關鍵交付**：
  - 執行歷史 Time-Travel Replay 與單節點 Playground。
  - 團隊協作、版本對比（Diff）、Eval 回歸測試儀表板與企業安全治理模組。
