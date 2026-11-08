# 02 · 方法与实现

> 本文描述"账本如何算、路由如何做、引擎如何升级、网关如何对外"。代码位置见每节末尾。

## 1. 总体链路

```
task.json ──> router(confidence) ──> CascadeEngine
                                      │
                    ┌─────────────────┴─────────────────┐
                    │                                   │
              small backend                      frontier backend
                    │                                   │
                    └──────────────> cost_record <───────┘
                                      │
                              metrics / ledger / gateway
```

关键约束：**路由与成本是纯函数**。模型调用只通过 `complete(task, attempt)` 抽象注入，因此账本逻辑可以用 mock 后端完整验证，再替换成真实 HTTP 后端。

## 2. 数据契约

四类对象，全部为严格 JSON（UTF-8、固定键名、不允许多余字段）：

| 对象 | 作用 | 关键字段 |
|---|---|---|
| `task` | 输入工作单元 | `task_id`, `kind`, `prompt`, `expected_difficulty`, `tags`, `created_at` |
| `route_decision` | 一次尝试的路由决策 | `policy`, `selected_model`, `confidence`, `escalated`, `reason` |
| `model_response` | 模型返回 | `model`, `content`, `success`, `latency_ms`, `usage`, 可选 `confidence` |
| `cost_record` | 任务级账本 | `model`, `attempts`, `cost_usd`, `latency_ms`, `success`, `cost_per_successful_task_usd` |

枚举：

- `kind`：`simple | medium | complex`
- `expected_difficulty`：`low | medium | high`
- `policy`：`all_frontier | cascade | all_small`
- `selected_model` / `model`：`small | frontier`

跨字段规则（schema 内与校验函数共同保证）：

- `usage.total_tokens = prompt_tokens + completion_tokens`
- 失败任务的 `cost_per_successful_task_usd` 必须为 `0`
- `cascade` 的升级决策必须选择 `frontier`；固定策略不允许升级

实现：[`cascade/src/schema.py`](../cascade/src/schema.py)。可用 `python3 cascade/src/schema.py --export` 导出到 `data/schema/`。

## 3. 合成任务流

`gen_tasks.py` 用固定模板与固定种子生成 100 条任务：

- 50 条 `simple`（天气、邮件归类、日程确认等）
- 30 条 `medium`
- 20 条 `complex`（跨平台比价、长程研究等）

> 初版规格建议约 80/20 的简单/复杂分布；实际采用 **50/30/20**，以便验证中档难度下的阈值行为。该偏离已在实现时明确记录；面板提供流量混合权重，可把结论外推到不同分布。

同一次运行两次输出字节一致；100 个 `task_id` 与 prompt 均唯一。产物：`data/synthetic/seed_tasks.jsonl`。

实现：[`cascade/src/gen_tasks.py`](../cascade/src/gen_tasks.py)。

## 4. 定价、重试溢价与 CPST

定价是纯数据（`cascade/configs/pricing.yaml`），单位为美元 / 百万 token：

| 模型 | 输入 | 输出 |
|---|---|---|
| `small` | 0.15 | 0.60 |
| `frontier` | 3.00 | 12.00 |

> 这是**示例价**，只为便于手算与演示，不代表任何厂商报价。

公式：

- 单次成本 = `prompt_tokens / 1e6 * input + completion_tokens / 1e6 * output`
- 期望尝试次数 = `1 / p`（p 为单次成功率）
- 重试溢价 = `1 / p - 1`；p=0.70 → 1.4286 次 → +42.86%
- **CPST** = 成功任务的总成本 ÷ 成功任务数

CPST 只对最终成功的任务计数，失败任务的浪费成本单独汇总为 `failed_cost_usd`，这样可以同时回答"成功要花多少钱"和"失败浪费了多少钱"。

实现：[`cascade/src/pricing.py`](../cascade/src/pricing.py)。

## 5. 路由器

路由器先用**确定性先验**：置信度由任务难度给出，并叠加一个由 `task_id` 哈希决定的稳定抖动（±0.03），让同难度任务也有差异。

接真实后端时，后端会请求 token `logprobs`，并把 `exp(平均 logprob)`（几何平均 token 概率）作为**模型自报置信度**；引擎在升级判定前用它覆盖先验。后端未返回 logprobs（mock 回放、provider 不支持、或设置 `CASCADE_LOGPROBS=0`）时，退回规则先验。

| 难度 | 基础置信度 |
|---|---|
| `low` | 0.93 |
| `medium` | 0.78 |
| `high` | 0.52 |

默认阈值 `confidence_threshold = 0.66`（`cascade/configs/policy.yaml`）。

规则：

- `all_frontier` → 直接选择 `frontier`，`confidence = 1.0`，不升级
- `all_small` → 选择 `small`，不升级；失败时按 `max_attempts = 2` 重试小模型
- `cascade` → 先选择 `small`；满足任一条件时升级 `frontier`：
  1. 小模型调用失败（fallback）
  2. 置信度 `< threshold`（quality check）

`max_attempts` 配置：

| 策略 | 最大尝试 |
|---|---|
| `all_frontier` | 1 |
| `all_small` | 2 |
| `cascade` | 1 次小模型 + 至多 1 次旗舰 |

实现：[`cascade/src/router.py`](../cascade/src/router.py)。

> 置信度来源优先级：模型自报 logprob 置信度 > 规则先验。`confidence_by_difficulty` 仅作为 fallback。若想进一步降低误升级，可在此基础上加入 self-consistency 或多 token margin 校准。

## 6. 级联引擎

`CascadeEngine` 与后端解耦，接收 `{small, frontier}` 两个实现了 `complete(task, attempt)` 的对象。每个任务输出：

```json
{
  "task_id": "task_0001",
  "policy": "cascade",
  "route_decisions": [ ... ],
  "responses": [ ... ],
  "cost_record": { ... }
}
```

三种策略的执行顺序：

- **all_frontier**：调用旗舰；失败时按配置最多重试到 `max_attempts`。
- **all_small**：调用小模型；失败则再试一次（默认 2 次上限）。
- **cascade**：
  1. 调用小模型（attempt = 1）；
  2. 若失败 → 升级旗舰，原因 `fallback`；
  3. 否则若置信度低于阈值 → 升级旗舰，原因 `quality check`；
  4. 成功 = 小模型成功 **或** 旗舰成功；成本 = 所有尝试之和。

关键点：

- 升级不是"重试小模型"，而是切换到旗舰；因此 `cascade` 的 `max_attempts` 不能简单理解为"同一模型重试次数"。
- 每次尝试都写入 `responses` 与 `route_decisions`，成本与延迟逐次累加后再生成 `cost_record`。
- 小模型响应带 `confidence` 时，首个决策的 `confidence` 与 `reason` 会同步更新为模型自报值。
- `export_trace()` 可输出人类可读的决策链，便于排障与 evidence。

实现：[`cascade/src/engine.py`](../cascade/src/engine.py)。

## 7. OpenAI 兼容网关

网关把标准 OpenAI 请求转换成 task，再交给引擎：

- `POST /v1/chat/completions`
  - 取最后一条 `role = user` 的消息作为 prompt；
  - 按 prompt 长度分类：≤120 字符 → `simple/low`，≤320 → `medium/medium`，否则 `complex/high`；
  - 构造 `task_id = req_<sha256(prompt + created_at)[:12]>`；
  - 返回标准 `id/object/created/model/choices/usage`，并附加 `cascade` 元信息（策略、置信度、是否升级、尝试次数、成本、决策链）。
- `GET /healthz`：返回 `status/policy/backends`；端点未配置时返回 `503` 与明确说明。
- `GET /v1/models`：返回最小模型列表，方便客户端探测。

安全与可靠性：

- 所有 endpoint/key 只从环境变量读取：`CASCADE_SMALL_BASE_URL`、`CASCADE_SMALL_MODEL`、`CASCADE_FRONTIER_BASE_URL`、`CASCADE_FRONTIER_MODEL`、`CASCADE_FRONTIER_API_KEY`。
- 传输错误（超时、HTTP 5xx、网络失败）返回 `success: false` 的响应，由引擎升级，不抛出异常。
- 网关错误只返回通用信息，不回显堆栈、URL 或密钥。
- 不支持流式；`stream: true` 返回 OpenAI 风格 `400`。

实现：[`cascade/src/gateway.py`](../cascade/src/gateway.py)、[`cascade/src/backends.py`](../cascade/src/backends.py)。

## 8. 确定性与配置

- 任务生成、置信度抖动、mock 响应都由稳定哈希决定；同输入同输出。
- 定价与策略是 YAML 纯数据；改阈值/价格不需要改代码。
- `replay.py` 一次跑完三策略，并写出：
  - `data/eval/mock_ledger.json`（完整 traces + metrics）
  - `data/eval/mock_ledger.md`（对比表）
  - `web/data/ledger.json`（面板所需的任务与逐次尝试原始响应）
- 面板在浏览器端用 `web/js/metrics.js` 重算；`node cascade/tests/verify_web_metrics.js` 会逐项比对 Python 指标。

## 9. Mock 边界

`MockBackend` 用固定概率与确定性抖动模拟成功/失败与 token 用量：

- 小模型成功率随难度下降，旗舰成功率更高；
- 失败响应也有 token 用量（prompt 已消耗，completion 为 0）；
- 延迟与 token 数由稳定哈希生成。

这些数字**只用于验证账本与产品交互**。真实模型行为、真实价格、真实延迟必须通过 F2.5 的 GPU/云端评测获得；在此之前，任何 mock 指标都必须在 UI 与文档中标注为 MOCK。
