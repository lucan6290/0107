# Code Review · `original_files/task1_classifier.py`

> 评审对象：`original_files/task1_classifier.py`

---

## 一、总体结论

脚本逻辑结构清晰、可读性尚可，能完成"30 条样本走通一遍"的最小闭环，但**离可上线、可评估、可复现仍有较大距离**。主要短板集中在四个方面：

1. **安全性**：API Key 明文硬编码，且文件可能被纳入 git。
2. **SDK 兼容性**：使用 openai < 1.0 的旧式全局 API，在 openai ≥ 1.0 环境下**直接抛错无法运行**。
3. **健壮性**：无任何异常处理、无重试、无断点；批量任务一条失败全盘崩溃。
4. **可评估性**：测试样本中带 `label`，但代码完全没用，没有 accuracy / 混淆矩阵 / 错误样本导出，**无法回答"这个 prompt 到底好不好"**。

---

## 二、问题清单（按严重程度分级）

| 序号 | 问题 | 影响 |
|----|------|------|
| 1  | **API Key 明文硬编码**：`openai.api_key = "sk-proj-..."` 直接写在源码里 | 一旦提交到 git/分享文件，Key 即泄露；无法区分 dev/prod 环境；轮换 Key 需改代码 |
| 2  | **OpenAI SDK 用法过时**：直接 `openai.api_key = ...` + `openai.chat.completions.create(...)`，这是 openai < 1.0 的全局式 API | 在 openai ≥ 1.0.0（2023-11 起为默认）环境下直接抛 `AttributeError: module 'openai' has no attribute 'api_key'`，**脚本根本跑不起来** |
| 3  | **无任何异常处理 + 批量结果在末尾才落盘**：`classify_question` 裸调 API，`batch_classify` 循环里也无 try/except，`json.dump` 在循环外 | 任一条遇到网络抖动 / 429 限流 / 5xx / JSON 解析失败 → 抛异常 → **前面已成功分类的全部丢失**；大批量场景下损失惨重 |
| 4  | **完全没有评估能力**：`task1_test_samples.json` 自带 `label` 字段，但脚本只输出 `predicted_category`，没有任何对比逻辑 | 无法回答"准确率多少"、"哪些类别最容易混"；prompt 改了也无法量化对比 → **改进 prompt 毫无依据** |
| 5  | **Prompt 设计过于简陋**：①只列类别名称，未引用 `categories.md` 中的定义和典型场景；②无 system prompt，role 弱；③无 few-shot；④未传达"`退款进度查询` 归退款退货而非物流查询"等歧义规则；⑤未说明多意图时如何取舍 | 在样本 21、24（多意图）、6（退款进度 vs 物流）、18（账号安全 vs 诈骗）等案例上极易翻车；"只回复类别名称"在无 few-shot 约束下不可靠 |
| 6  | **输出未做白名单校验**：`response.choices[0].message.content.strip()` 直接返回 | 模型可能输出 `分类结果：退款退货。`、`退款退货（用户要求退货）`、英文标点等变体；评估时 string 比较直接 False → accuracy 虚低 |
| 7  | **输入文件 / 字段未校验**：假设文件存在、JSON 格式正确、每个 item 都有 `id` 和 `question` | 文件缺失 / JSON 错误 / 字段缺失 → 抛 `FileNotFoundError` / `JSONDecodeError` / `KeyError`，错误信息不友好 |
| 8  | **缺少日志体系**：全程靠 `print`，无级别、无时间戳、无文件落地 | 跑批后无法回溯"哪条慢、哪条失败、消耗多少 token"；评估时无法对账 |
| 9  | **缺少 mock 模式**：无 `OPENAI_API_KEY` 时直接退出，无法本地/CI 跑通流程 | 无网环境下完全无法验证管道是否正常 |
| 10 | **缺少重试机制**：429 / 502 / 503 等瞬时错误一次就放弃 | 批量场景下偶发限流会让整批失败 |
| 11 | **无并发控制**：30 条样本顺序调用，每条 1-2s 即 30-60s | 批量场景慢；扩展到上千条几乎不可用 |

---
