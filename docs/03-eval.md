# 03 · 评测、账本与边界

> 所有数字默认来自 `data/eval/mock_ledger.json`（确定性 mock 后端），不是真实模型测量值。真实后端目前只有 20 条任务的试点（含 LLM 判定），仍不作为生产结论，详见第 8 节。

## 1. 评测问题

评测只回答三个问题：

1. 在**同一任务流**上，三种架构的总成本、CPST、成功率、升级率、延迟差多少？
2. 级联的"升级"是否真的发生在需要升级的任务上，原因是否可追溯？
3. 浏览器面板展示的数字，是否与本地 Python 账本完全一致？

不回答（本期范围外）：

- 真实模型的质量差异（需要人工标注或任务级评分标准）；
- 学习型路由器的收益；
- 生产流量下的长期成本分布。

## 2. 评测设置

| 项 | 值 |
|---|---|
| 任务流 | 100 条合成任务，固定种子，`simple/medium/complex = 50/30/20` |
| 定价 | 示例价：small 0.15/0.60，frontier 3.00/12.00 USD / 1M tokens |
| 阈值 | 0.66 |
| 小模型重试上限（all_small） | 2 |
| 后端 | 确定性 `MockBackend`（不是真实模型） |
| 成功定义 | 模型响应 `success = true`；任务成功 = 任一尝试成功 |

## 3. 指标定义

| 指标 | 定义 |
|---|---|
| 总成本 `total_cost_usd` | 该策略所有尝试成本之和 |
| CPST `cpst_usd` | 成功任务的总成本 ÷ 成功任务数 |
| 成功率 `success_rate` | 成功任务数 ÷ 总任务数 |
| 升级率 `escalation_rate` | 至少发生一次升级的任务 ÷ 总任务数 |
| 平均延迟 `avg_latency_ms` | 每个任务所有尝试延迟之和的平均 |
| 平均尝试 `avg_attempts` | 每个任务尝试次数的平均 |
| 失败浪费 `failed_cost_usd` | 最终失败任务上花掉的钱 |
| 节省比例 `savings_vs_frontier` | `1 - 本策略总成本 / 全旗舰总成本` |

要点：CPST 的分子只包含成功任务，但成功任务内部**包含**失败重试与升级花费；失败任务的钱单独计入 `failed_cost_usd`，不会从分母里"消失"。

## 4. Mock 结果

| 策略 | 总成本 | CPST | 成功率 | 升级率 | 平均延迟 | 平均尝试 | 失败浪费 | 节省 |
|---|---|---|---|---|---|---|---|---|
| `all_frontier` | $0.235848 | $0.002378 | 98% | 0% | 824 ms | 1.00 | $0.002778 | 0% |
| `cascade` | $0.118222 | $0.001184 | 99% | 29% | 660 ms | 1.29 | $0.001031 | **49.87%** |
| `all_small` | $0.011840 | $0.000113 | 93% | 0% | 394 ms | 1.24 | $0.001361 | 94.98% |

怎么读这张表：

- **级联不是"更便宜的全旗舰"**：它用 29% 的升级率，把 99% 的任务做成功，同时把总成本砍到全旗舰的约一半。
- **全小模型最便宜，但成功率掉到 93%**：失败任务浪费 $0.001361，已经超过级联的全部失败浪费（$0.001031）。便宜的单次价格不等于低的成功成本。
- **全旗舰成功率 98% 并非 100%**：mock 后端也会失败，失败同样产生浪费；这正是 CPST 要纳入失败成本的原因。
- **延迟与成本不同步**：全小模型平均最快，级联居中，全旗舰最慢；升级会在长尾任务上付出延迟代价。

> 以上全部为 MOCK。任何对外引用必须同时标注 mock 口径与示例定价。

## 5. 口径一致性（Python ↔ 浏览器）

面板不是"预渲染一张表"，而是在浏览器里用原始逐次响应重算：

1. `replay.py` 把每个任务的 small/frontier 尝试原始响应写入 `web/data/ledger.json`；
2. `web/js/metrics.js` 用与 `engine.py` / `pricing.py` 相同的规则重算成本、成功、升级与汇总；
3. `node cascade/tests/verify_web_metrics.js` 对 7 个指标逐项比对，误差超过阈值即退出非 0。

验证输出（默认参数）：

```
ledger mode: mock | tasks: 100
  all_frontier OK cost=0.235848 cpst=0.002378 success=98.0% escalation=0.0% savings=0.0%
  cascade      OK cost=0.118222 cpst=0.001184 success=99.0% escalation=29.0% savings=49.9%
  all_small    OK cost=0.011840 cpst=0.000113 success=93.0% escalation=0.0% savings=95.0%
web metrics match the Python ledger
```

## 6. 复现命令

```bash
python3 cascade/src/gen_tasks.py
python3 cascade/src/replay.py
python3 -m pytest cascade/tests/ -q
node cascade/tests/verify_web_metrics.js
```

产物：

- `data/synthetic/seed_tasks.jsonl`
- `data/eval/mock_ledger.json` / `.md`
- `web/data/ledger.json`

## 7. 失败案例与可追溯性

- `cascade` 的 fallback 路径：小模型失败 → 旗舰尝试；`reason` 以 `fallback` 开头。
- `cascade` 的质量路径：小模型成功但置信度低于阈值 → 旗舰尝试；`reason` 以 `quality check` 开头。
- 两种路径都由 `test_engine.py` 用脚本化后端强制触发，避免"碰巧通过"。
- `export_trace()` 输出形如 `task_0001 (cascade) -> small ... -> frontier ...` 的决策链，可直接贴进 evidence。

## 8. 真实后端评测（F2.5）：20 条任务试点

真实链路已跑通：`qwen-plus`（小模型）→ `qwen-max`（旗舰），OpenAI 兼容端点，价格用官方千问价（`cascade/configs/pricing.qwen.yaml`，汇率 7.2；small 0.111/0.278、frontier 0.333/1.333 USD / 1M tokens）。样本是从 100 条种子任务中均匀抽取的 20 条（simple 11 / medium 6 / complex 3），两种角色统一 `max_tokens=1024`，结果单独保存在 `data/eval/real_ledger.json`，不与 mock 账本合并。

### 8.1 服务层结果（HTTP 成功口径）

| 策略 | 总成本 | CPST | 成功率 | 升级率 | 平均延迟 | 平均尝试 | 相对全旗舰 |
|---|---|---|---|---|---|---|---|
| `all_frontier` | $0.005683 | $0.000284 | 100% | 0% | 6671 ms | 1.000 | 0% |
| `cascade` | $0.002954 | $0.000148 | 100% | 0% | 12188 ms | 1.000 | **48.03%** |
| `all_small` | $0.002962 | $0.000148 | 100% | 0% | 12346 ms | 1.000 | 47.89% |

怎么读：

- 统一输出预算后，级联/全小模型相对全旗舰**省约 48%**，与 mock 的 49.87% 惊人地接近——5 条试点时只有 1%–6%，说明当时的差距主要是小模型冗长输出造成的假象（qwen-plus 曾单任务生成 2342 个 completion token，现在被 1024 上限截断）。
- **升级率为 0%**：qwen-plus 自报置信度中位数 0.8958、最低 0.8023，全部高于阈值 0.66，cascade 实际上退化成了 all_small（两者成本差 $0.000008 只是请求顺序差异）。
- qwen-max 的自报置信度恒为 1.0，疑似该模型不返回有效 logprobs；置信度信号目前只在 qwen-plus 上可信。

### 8.2 判定口径（LLM-as-a-Judge）

HTTP 成功不等于任务被解决。离线判定（`cascade/src/judge.py` / `judge_ledger.py`，严格 rubric、温度 0、判定不感知策略）把"请提供更多信息"式回答判为失败；判定器自身调用失败（超时/限流）计入 `judge_failures`，**不进判定分母**。

| 策略 | 任务 | 判定成功 | 判定成功率 | CPST（仅服务） | CPST（含判定） | 失败浪费 | 判定成本 |
|---|---|---|---|---|---|---|---|
| `all_frontier` | 20（6 条判定失败） | 10/14 | 71.4% | $0.000421 | $0.000665 | $0.001810 | $0.002446 |
| `cascade` | 20 | 19/20 | 95.0% | $0.000140 | $0.000427 | $0.000308 | $0.005442 |
| `all_small` | 20 | 19/20 | 95.0% | $0.000141 | $0.000427 | $0.000308 | $0.005437 |

怎么读：

- **判定口径下级联优势扩大**：all_frontier 有 4 条真实质量失败（回答只索要更多信息），按"成功任务成本"口径 CPST 涨到 $0.000421，是 cascade（$0.000140）的 3 倍。qwen-max 回答简短（completion token 中位数 101 vs qwen-plus 545），简短回答更容易不满足严格 rubric。
- cascade / all_small 唯一的失败是 `task_0066`：预算约束确实被违反（交通费超支），判定成立。
- 判定成本（$0.0024–$0.0054）再次高于服务成本；含判定后 `all_frontier` 仍是 $0.000665，排名不变但差距缩小。**判定是评测成本，不进线上 CPST**。

### 8.3 复现

```bash
# 真实三策略（需要 DASHSCOPE_API_KEY，或 CASCADE_SMALL_* / CASCADE_FRONTIER_* 环境变量）
python3 cascade/src/real_eval.py --limit 20 --max-tokens 1024 \
    --pricing cascade/configs/pricing.qwen.yaml
# 离线判定（读取上一步的真实账本，不重新生成答案）
python3 cascade/src/judge_ledger.py --ledger data/eval/real_ledger.json
```

产物：`data/eval/real_ledger.{json,md}`、`data/eval/real_ledger_judged.{json,md}`。

### 8.4 得出生产结论前的必做项

1. 样本扩到 50–100 条并按难度分层；当前 complex 只有 3 条，高难度层结论不可信。
2. 换一个非 qwen-max 的模型做裁判（当前裁判与被测的 all_frontier 答案同源，存在 self-preference 风险），或做双裁判交叉校验。
3. 用 top-1/top-2 logprob margin 或自一致性替代平均 token 概率，并按真实分布重新校准阈值——当前 0.66 阈值下升级率 0%，置信度信号没有起到筛选作用。
4. 判定调用本身需要重试与告警：6/20 的 judge failure 率（all_frontier 列）说明裁判通道不够稳。

## 9. 已知限制

- `success` 在 mock 中是概率事件，不代表真实答案质量；真实评测需要任务级 rubric 或人工标注。
- 置信度来自规则 + 稳定抖动；真实试点已确认 qwen-plus 平均 token 概率（0.80–0.99）全部高于阈值 0.66，升级率 0%，生产前必须重新校准。
- 小模型输出长度差异会主导真实成本；真实评测已统一 `max_tokens=1024`，比较策略前必须固定输出预算。
- 定价是示例值（mock）与官方千问价（真实）各一套；任何成本结论都必须注明用的是哪套价格与汇率。
- 20 条真实任务只是试点：方向性信号（统一预算后省约 48%、判定口径下 CPST 差 3 倍）可引用，绝对数字不构成生产结论；mock 的 100 条任务只用于验证账本与交互。
- 判定器本身有偏差和成本（判定花费高于服务花费），且当前裁判与被测旗舰模型同源；`CPST（含判定）` 与仅服务成本必须分开报告，判定器自身失败单独计数。
