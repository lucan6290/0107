# 项目规范 · CLAUDE.md

> 本文件为 Claude Code 在本项目内的强制约束。所有开发行为须遵守。

## 项目目标

对客服 FAQ 自动分类脚本（`task1_classifier.py`）进行 **Code Review 并改进**，覆盖：
Code Review、Prompt 改进、评估对比、工程化重构、README。

## 目录约定

| 目录 | 用途 | 是否可修改 |
|------|------|-----------|
| `original_files/` | 原始任务文件（classifier、prompt、categories、test_samples） | **禁止修改**，作为改进前基线 |
| `src/` | 改进后源码（`config.py` / `prompt_loader.py` / `classifier.py` / `batch.py` / `evaluate.py`） | 可修改 |
| `results/` | 评估结果输出（predictions、eval、混淆矩阵、日志） | 可写入，已被 `.gitignore` 忽略具体内容 |
| `prompts/` | prompt 文件（v1 / v2） | 可修改 |
| `tests/` | 测试代码 | 可修改 |
| `docs/` | 内部文档（不上传 GitHub，已被 `.gitignore` 忽略） | 可修改 |

## 代码风格

- **PEP 8**（用 `black` / `ruff` 格式化）
- **类型注解**：函数签名必须标注参数与返回类型
- **Google 风格 docstring**：每个模块、类、公开函数都要写

## 运行模式（关键）

无 `OPENAI_API_KEY` 环境变量时，**自动切换 mock 模式**运行：
- 有 `OPENAI_API_KEY` → 走真实 OpenAI API
- 无 `OPENAI_API_KEY` → 走基于关键词规则的 `MockClassifier`，确保评估流程可跑通

mock 模式必须在 README 与运行日志中**诚实标注**。

## 提交规范

遵循全局规范：
- commit message 使用**纯中文**
- 格式：`类型: 简要描述`（feat / fix / docs / style / refactor / test / chore）
- 单次提交仅包含一个功能或修复
