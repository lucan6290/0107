"""配置加载模块。

从项目根目录的 `.env` 文件以及环境变量中读取运行时配置。
所有其他模块统一从这里取值，避免散落的硬编码。
"""
import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent

load_dotenv(PROJECT_ROOT / ".env")

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

PROMPT_FILE: Path = PROJECT_ROOT / "docs" / "prompt_v2.md"
