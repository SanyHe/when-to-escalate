# Calibration Analysis (OFFLINE)

> OFFLINE: reuses recorded answers and judged verdicts; no model was called. Each ledger has 50 tasks, so treat differences under ~5pp and sparse high-confidence bins as noise.

## Summary

| Run | Scored | Accuracy | Mean conf | Conf (correct) | Conf (wrong) | ECE | Brier | AUC |
|---|---|---|---|---|---|---|---|---|
| qwen-plus-baseline | 50/50 | 28.0% | 0.868 | 0.888 | 0.860 | 0.588 | 0.538 | 0.704 |
| qwen-plus-brief | 50/50 | 44.0% | 0.857 | 0.883 | 0.836 | 0.417 | 0.401 | 0.693 |
| qwen-flash | 50/50 | 10.0% | 0.854 | 0.812 | 0.859 | 0.754 | 0.670 | 0.258 |

Accuracy below mean confidence means overconfidence. AUC measures how well confidence ranks correct answers above wrong ones; 0.5 is chance.

## Escalation confusion at threshold 0.85

| Run | Escalated | Caught wrong | Wasted on correct | Kept wrong |
|---|---|---|---|---|
| qwen-plus-baseline | 17 (34%) | 15 | 2 | 21 |
| qwen-plus-brief | 16 (32%) | 12 | 4 | 16 |
| qwen-flash | 26 (52%) | 22 | 4 | 23 |

## Reliability — qwen-plus-baseline

| Bin | n | Mean conf | Accuracy | Gap |
|---|---|---|---|---|
| 0.8–0.9 | 37 | 0.850 | 18.9% | -0.661 |
| 0.9–1.0 | 13 | 0.920 | 53.8% | -0.381 |

## Reliability — qwen-plus-brief

| Bin | n | Mean conf | Accuracy | Gap |
|---|---|---|---|---|
| 0.6–0.7 | 1 | 0.665 | 0.0% | -0.665 |
| 0.7–0.8 | 4 | 0.725 | 0.0% | -0.725 |
| 0.8–0.9 | 36 | 0.860 | 41.7% | -0.443 |
| 0.9–1.0 | 9 | 0.926 | 77.8% | -0.148 |

## Reliability — qwen-flash

| Bin | n | Mean conf | Accuracy | Gap |
|---|---|---|---|---|
| 0.7–0.8 | 8 | 0.780 | 25.0% | -0.530 |
| 0.8–0.9 | 31 | 0.845 | 9.7% | -0.748 |
| 0.9–1.0 | 11 | 0.935 | 0.0% | -0.935 |

## Threshold frontier (from each ledger's recorded sweep)

| Run | Threshold | Escalation | Judged success | Total cost |
|---|---|---|---|---|
| qwen-plus-baseline | 0.600 | 0% | 28% | $0.007486 |
| qwen-plus-baseline | 0.700 | 0% | 28% | $0.007486 |
| qwen-plus-baseline | 0.800 | 0% | 28% | $0.007486 |
| qwen-plus-baseline | 0.850 | 34% | 50% | $0.015950 |
| qwen-plus-baseline | 0.900 | 74% | 72% | $0.023331 |
| qwen-plus-baseline | 0.950 | 98% | 78% | $0.025682 |
| qwen-plus-brief | 0.600 | 0% | 44% | $0.001768 |
| qwen-plus-brief | 0.700 | 2% | 46% | $0.001796 |
| qwen-plus-brief | 0.800 | 10% | 54% | $0.001908 |
| qwen-plus-brief | 0.850 | 32% | 66% | $0.007126 |
| qwen-plus-brief | 0.900 | 82% | 80% | $0.018454 |
| qwen-plus-brief | 0.950 | 96% | 80% | $0.020616 |
| qwen-flash | 0.600 | 0% | 10% | $0.000951 |
| qwen-flash | 0.700 | 0% | 10% | $0.000951 |
| qwen-flash | 0.800 | 16% | 16% | $0.005179 |
| qwen-flash | 0.850 | 52% | 44% | $0.012203 |
| qwen-flash | 0.900 | 78% | 64% | $0.016400 |
| qwen-flash | 0.950 | 98% | 78% | $0.019729 |
| qwen-flash | 1.000 | 100% | 80% | $0.019817 |

All costs reuse the recorded ledger spend under its own pricing file; this report does not re-price anything.
