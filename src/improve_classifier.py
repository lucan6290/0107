#!/usr/bin/env python3
# python src/improve_classifier.py original_files/task1_test_samples.json results/predictions_v2.json.json

"""客服 FAQ 自动分类脚本（v2 改进版，单文件交付）。

基于 original_files/task1_classifier.py

特性：
- 安全：API Key 从 .env / 环境变量读取，无硬编码
- 兼容：基于 langchain-openai 的 ChatOpenAI
- 健壮：异常重试（指数退避）+ 输入校验 + 输出白名单 + 失败隔离
- 可测：无 OPENAI_API_KEY 时自动切 mock 模式
- Prompt：内嵌 v2（system + user，含完整类别定义 + 3 条冲突规则 + 4 条 few-shot）

CLI:
    python -m src.improve_classifier <input.json> <output.json>
    python src/improve_classifier.py <input.json> <output.json>
    <input.json>: original_files/task1_test_samples.json
    <output.json>:results/predictions_v2.json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI


# ============================================================
# 配置
# ============================================================

load_dotenv()

OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "").strip()
OPENAI_BASE_URL: str = os.environ.get("OPENAI_BASE_URL", "").strip()
OPENAI_MODEL: str = os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip()

USE_MOCK: bool = not OPENAI_API_KEY

VALID_CATEGORIES: list[str] = [
    "退款退货",
    "物流查询",
    "账号问题",
    "商品咨询",
    "投诉建议",
    "其他",
]

DEFAULT_CATEGORY: str = "其他"


# ============================================================
# 内嵌 v2 Prompt
# ============================================================

SYSTEM_PROMPT: str = """你是电商客服工单智能分类助手。你的职责是把用户提交的一条问题准确归入下列 6 个合法类别之一：

- 退款退货
- 物流查询
- 账号问题
- 商品咨询
- 投诉建议
- 其他

【输出约束】（必须严格遵守）

1. 只输出上述 6 个类别名之一，原样输出，不得修改任何字符（包括简写、近义词、英文翻译）。
2. 不得添加任何前缀，例如"分类结果："、"答案："、"类别："。
3. 不得添加任何解释、推理过程、置信度、备注。
4. 不得添加任何标点符号（包括句号、顿号、引号、括号、冒号）。
5. 若问题含义模糊、信息不足、或确属闲聊/无法归类，输出"其他"。

【错误示例】（以下输出均为禁止）

- "分类结果：退款退货"            （有前缀）
- "退款退货。"                    （有标点）
- "应该是退款退货"                （有解释）
- "退款退货（用户要求退货）"      （有括号备注）
- "Refund"                        （非中文类别名）
- "退款退货、物流查询"            （输出了多个类别）

【正确示例】

- 退款退货    
- 物流查询    
- 其他        """

USER_TEMPLATE: str = """请对下面这条用户问题进行分类。

【分类类别定义】

| 类别     | 定义                                           | 典型场景                                                       |
|----------|------------------------------------------------|----------------------------------------------------------------|
| 退款退货 | 用户要求退款、退货、换货，或咨询退款进度       | "我要退货"、"钱什么时候退回来"、"怎么换货"                     |
| 物流查询 | 用户询问包裹位置、配送状态、快递信息           | "快递到哪了"、"什么时候能到"、"包裹显示签收但没收到"           |
| 账号问题 | 用户遇到登录、密码、账号安全等问题             | "密码忘了怎么办"、"账号被锁了"、"怎么修改手机号"               |
| 商品咨询 | 用户询问商品信息、规格、库存、价格等           | "这个商品有蓝色的吗"、"尺码怎么选"、"什么时候补货"             |
| 投诉建议 | 用户对服务、商品质量不满，或提出建议           | "你们服务太差了"、"我要投诉"、"建议你们加个XX功能"             |
| 其他     | 不属于以上任何类别的问题                       | 闲聊、无具体诉求、无法归类的表述                               |

【冲突处理规则】（当问题落在类别边界时，按以下规则裁决，优先级高于一般判断）

规则 1 · 退款进度查询 → 归「退款退货」，不归「物流查询」。
  - 凡是问"退款到哪一步了""退款什么时候到账""退款进度"的，都属于退款流程的一部分，
    即使措辞里出现了"什么时候到""到账"等接近物流的词，也归「退款退货」。

规则 2 · 多类别诉求 → 以「用户的主要诉求」为准。
  - 判断方法：用户最希望被首先解决的核心问题是什么？
  - 附带提及、顺便问的次要问题不计入分类。
  - 若难以分辨主次，归入与"用户付出的行动 / 期望的处置"最直接相关的类别。

规则 3 · 辱骂/情绪化表述 → 看是否含具体投诉内容。
  - 含具体投诉内容（针对商品质量、服务态度、流程问题的指责、举报、建议）→「投诉建议」
  - 纯辱骂、纯情绪发泄、无具体投诉对象或内容 →「其他」

【few-shot 示例】（输入 → 输出，请按此格式输出，仅输出类别名）

示例 1
输入：退款什么时候到账
输出：退款退货

示例 2
输入：买了三天就坏了，什么破质量
输出：投诉建议

示例 3
输入：你好
输出：其他

示例 4
输入：我想问下这个退款的事顺便看看快递到没到
输出：退款退货

【待分类问题】

用户问题：{question}"""


# ============================================================
# Logging
# ============================================================

logger = logging.getLogger("improve_classifier")


def setup_logging(verbose: bool = False) -> None:
    """配置日志：INFO 默认，-v 开 DEBUG。"""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True,
    )


# ============================================================
# 输出归一化与白名单校验
# ============================================================

_PUNCT_RE = re.compile(r"[，。！？；：、,.!?;:\"'()\[\]（）【】\s]+")


def normalize_output(raw: str) -> str:
    """规范化模型输出：去常见中英文标点 + 折叠空白。

    Args:
        raw: 模型原始返回字符串。

    Returns:
        清理后的字符串。
    """
    return _PUNCT_RE.sub("", raw).strip()


def validate_category(text: str) -> str:
    """白名单校验。命中合法类别则原样返回；否则尝试包含匹配；仍失败归"其他"并告警。

    Args:
        text: 规范化后的字符串。

    Returns:
        VALID_CATEGORIES 之一。
    """
    if text in VALID_CATEGORIES:
        return text
    for cat in VALID_CATEGORIES:
        if cat in text:
            logger.warning("输出未严格命中白名单，使用包含匹配: %r -> %r", text, cat)
            return cat
    logger.warning("输出不在合法类别内，归为 %r: %r", DEFAULT_CATEGORY, text)
    return DEFAULT_CATEGORY


# ============================================================
# 真实 API 模式
# ============================================================

def build_llm() -> ChatOpenAI:
    """根据环境变量构造 ChatOpenAI 客户端。"""
    kwargs: dict = {
        "model": OPENAI_MODEL,
        "api_key": OPENAI_API_KEY,
        "temperature": 0,
        "max_tokens": 20,
    }
    if OPENAI_BASE_URL:
        kwargs["base_url"] = OPENAI_BASE_URL
    return ChatOpenAI(**kwargs)


def _invoke_with_retry(
    llm: ChatOpenAI,
    system_prompt: str,
    user_content: str,
    max_attempts: int = 3,
) -> str:
    """调用 LLM，失败时指数退避（1s/2s/4s）重试。

    Args:
        llm: ChatOpenAI 客户端。
        system_prompt: system 消息内容。
        user_content: user 消息内容（已替换占位符）。
        max_attempts: 最大尝试次数（含首次）。

    Returns:
        模型返回的文本。

    Raises:
        最后一次重试仍失败的原始异常。
    """
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_content),
    ]
    last_err: Optional[Exception] = None
    for attempt in range(1, max_attempts + 1):
        try:
            t0 = time.time()
            response = llm.invoke(messages)
            logger.debug("LLM 调用成功 (%.2fs)", time.time() - t0)
            return response.content if response.content is not None else ""
        except Exception as e:
            last_err = e
            if attempt == max_attempts:
                logger.error("LLM 调用失败，已达最大重试次数 %d: %s", max_attempts, e)
                raise
            wait = 2 ** (attempt - 1)
            logger.warning(
                "LLM 调用失败（%s），%ds 后重试 (%d/%d)",
                type(e).__name__, wait, attempt, max_attempts,
            )
            time.sleep(wait)
    assert last_err is not None
    raise last_err


def classify_real_api(question: str, llm: ChatOpenAI) -> str:
    """真实 API 模式分类一条问题。"""
    user_content = USER_TEMPLATE.replace("{question}", question)
    raw = _invoke_with_retry(llm, SYSTEM_PROMPT, user_content)
    return validate_category(normalize_output(raw))


# ============================================================
# Mock 模式（无 OPENAI_API_KEY 时自动启用）
# ============================================================

MOCK_KEYWORDS: dict[str, list[str]] = {
    "退款退货": ["退款", "退货", "换货", "退钱", "退回", "退款进度", "到账"],
    "物流查询": ["快递", "包裹", "配送", "签收", "物流", "到了没", "派送"],
    "账号问题": ["密码", "登录", "账号", "手机号", "冻结", "异地", "短信验证"],
    "商品咨询": ["有没有", "什么材质", "支持", "能带", "尺码", "颜色", "库存", "规格"],
    "投诉建议": ["投诉", "举报", "太差", "建议", "质量有问题", "坏了"],
}

SMALLTALK_EXACT: set[str] = {
    "你好", "您好", "hi", "hello", "谢谢", "感谢",
    "嗯嗯", "好的", "ok", "？", "?", "？？？",
}


def _is_smalltalk(text: str) -> bool:
    """检测纯闲聊。"""
    text = text.strip()
    if not text:
        return True
    if text.lower() in SMALLTALK_EXACT:
        return True
    if all(c in "？?！!.,，。、 ~" for c in text):
        return True
    return False


def classify_mock(question: str) -> str:
    """Mock 模式分类。覆盖 categories.md 中的冲突规则。"""
    text = question.strip()
    if _is_smalltalk(text):
        return "其他"

    hits: dict[str, list[str]] = {
        cat: [kw for kw in kws if kw in text]
        for cat, kws in MOCK_KEYWORDS.items()
    }

    if hits["退款退货"] and hits["物流查询"]:
        logger.debug("Mock 命中冲突规则（退款+物流 → 退款退货）: %r", text)
        return "退款退货"

    for cat in ("投诉建议", "退款退货", "物流查询", "账号问题", "商品咨询"):
        if hits[cat]:
            return cat

    return DEFAULT_CATEGORY


# ============================================================
# 统一入口
# ============================================================

def classify_question(
    question: str,
    llm: Optional[ChatOpenAI] = None,
) -> str:
    """分类单条问题。Mock 模式忽略 llm 参数。

    Args:
        question: 待分类的用户问题。
        llm: 已构造的 ChatOpenAI 客户端；mock 模式可为 None。

    Returns:
        VALID_CATEGORIES 之一；分类失败时由调用方决定（此处不捕获异常）。
    """
    if USE_MOCK:
        return classify_mock(question)
    assert llm is not None, "真实 API 模式下 llm 不能为 None"
    return classify_real_api(question, llm)


def _load_input(input_file: Path) -> list[dict]:
    """读取输入 JSON 文件，做基本格式校验。"""
    try:
        with open(input_file, encoding="utf-8") as f:
            items = json.load(f)
    except FileNotFoundError:
        logger.error("输入文件不存在: %s", input_file)
        sys.exit(1)
    except json.JSONDecodeError as e:
        logger.error("输入文件 JSON 解析失败: %s", e)
        sys.exit(1)
    if not isinstance(items, list):
        logger.error(
            "输入 JSON 必须是数组（list），当前是 %s", type(items).__name__
        )
        sys.exit(1)
    if not items:
        logger.warning("输入文件为空数组，将输出空结果")
    return items


def batch_classify(input_file: Path, output_file: Path) -> None:
    """批量分类。读取 input，逐条分类，写入 output。

    单条失败不影响整批（记 "ERROR" 继续），输出保留 label 字段以便评估。
    """
    items = _load_input(input_file)

    llm: Optional[ChatOpenAI] = None
    if USE_MOCK:
        logger.warning(
            "运行模式: Mock（OPENAI_API_KEY 未设置，结果仅用于流程验证）"
        )
    else:
        logger.info("运行模式: 真实 API (model=%s)", OPENAI_MODEL)
        llm = build_llm()

    results: list[dict] = []
    n = len(items)
    for i, item in enumerate(items, 1):
        item_id = item.get("id")
        question = item.get("question", "")
        try:
            category = classify_question(question, llm)
        except Exception as e:
            logger.error("id=%s 分类失败，记录为 ERROR: %s", item_id, e)
            category = "ERROR"
        results.append({
            "id": item_id,
            "question": question,
            "label": item.get("label", ""),
            "predicted_category": category,
        })
        if i % 10 == 0 or i == n:
            logger.info("进度 %d/%d", i, n)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    logger.info("分类完成，共 %d 条，写入 %s", len(results), output_file)


# ============================================================
# CLI
# ============================================================

def main() -> None:
    """命令行入口。

    用法：
        python -m src.improve_classifier <input.json> <output.json>
    """
    parser = argparse.ArgumentParser(
        description="客服 FAQ 分类器 v2（单文件改进版）",
    )
    parser.add_argument("input", help="输入 JSON 文件路径")
    parser.add_argument("output", help="输出 JSON 文件路径")
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="启用 DEBUG 日志"
    )
    args = parser.parse_args()

    setup_logging(args.verbose)
    batch_classify(Path(args.input), Path(args.output))


if __name__ == "__main__":
    main()
