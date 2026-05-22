# 📚 FcstLabPro 文档索引

## 目录结构

```
docs/
├── README.md                 ← 本文件
├── specs/                    ← 🔥 架构规格文档
│   └── data_pipeline.md      ←    数据链路完整文档 (E1/E8)
├── cr_0308*.md               ← 代码审查报告
├── guides/                   ← LLM Prompt 模板 & 开发指南
├── proposals/                ← 策略提案 & 技术讨论
└── references/               ← 外部论文 & 学术参考
```

## 核心架构文档

| 文件 | 说明 |
|------|------|
| **`specs/data_pipeline.md`** | **数据链路完整文档**：数据源清单、训练 vs 推理同构、生产 8 步流水线、故障回退 |
| `cr_0308.md` | 代码审查报告 (2026-03-08) |
| `cr_0308_paper_comparison.md` | 与 arXiv 论文对比 |
| `cr_0308_reusability.md` | 可复用性 / DRY 违规识别 |

## guides/ — 指南与 Prompt

| 文件 | 说明 |
|------|------|
| `code-reviewer-guide.md` | Python 代码审查 Prompt (PEP8、类型、性能、异步) |
| `mle-guide.md` | ML 工程代码审查 Prompt (数据泄露、可复现、评估规范) |

## proposals/ — 提案与讨论

| 文件 | 说明 | 日期 |
|------|------|------|
| `llm_strategy_proposal.md` | LLM 增强交易策略方案 | 2026-02-13 |
| `btc_monthly_forecast_discussion_20260302.md` | BTC 月线预测可行性讨论 | 2026-03-02 |

## references/ — 外部参考

| 文件 | 说明 |
|------|------|
| `zhihu_article_1954268140042195782.md` | NeurIPS 2025 时间序列论文总结 (上·预测) |
| `zhihu_article_2005128847935432360.md` | ICLR 2026 时间序列论文总结 (下·分类/异常/LLM) |
