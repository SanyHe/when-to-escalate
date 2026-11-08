# 03 · 评测、账本与边界

> 所有数字默认来自 `data/eval/mock_ledger.json`（确定性 mock 后端），不是真实模型测量值。真实后端评测（F2.5）目前 **blocked**，原因见第 8 节。

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

## 8. 真实后端评测（F2.5）：Blocked

F2.5 需要在真实小模型（vLLM）与真实旗舰 endpoint 上跑同一任务流，并与 mock 口径分开报告。当前环境缺少：

- GPU 主机或可用的 vLLM 服务；
- 旗舰模型的 endpoint 与凭据（只能通过环境变量注入）。

因此 F2.5 标记为 **blocked**，而不是 passing。解除阻塞后应执行：

1. `export CASCADE_SMALL_BASE_URL=...` / `CASCADE_FRONTIER_*`；
2. 用真实后端跑三策略，记录成功率、延迟、token 用量与失败原因；
3. 把真实账本另存为 `data/eval/real_ledger.json`，与 mock 账本分表展示；
4. 只有真实数据支持时，才可以对外声称"级联降低 CPST"的生产结论。

## 9. 已知限制

- `success` 在 mock 中是概率事件，不代表真实答案质量；真实评测需要任务级 rubric 或人工标注。
- 置信度来自规则 + 稳定抖动，不是模型自带的校准信号；真实部署应替换为 logprob margin、self-consistency 或学习型分类器。
- 定价是示例值；任何真实成本结论都必须先替换为当前官方价格。
- 100 条任务只用于验证账本与交互；生产结论需要更大样本与分布外任务。
