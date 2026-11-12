"""Opt-in local enterprise demo. Read before initializing the database."""
import os
from pathlib import Path
from urllib.parse import urlsplit

ENABLED = os.getenv("ENTERPRISE_DEMO") == "1"
ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:3001")
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / "data" / "enterprise-demo.sqlite3"


def demo_database_url() -> str:
    path = Path(os.getenv("ENTERPRISE_DEMO_DB", str(DEFAULT_DB))).resolve()
    # Custom files are useful for isolated tests. Never open the normal app DB.
    if path != DEFAULT_DB.resolve() and (
        not path.is_relative_to((ROOT / ".tmp").resolve())
        or path.suffix != ".sqlite3"
    ):
        raise RuntimeError("企业演示数据库必须使用默认路径或 .tmp 下的独立 .sqlite3 文件")
    origin = urlsplit(ORIGIN)
    if origin.scheme not in {"http", "https"} or origin.hostname not in {"localhost", "127.0.0.1"} or origin.path or origin.query or origin.fragment or origin.username:
        raise RuntimeError("企业演示仅支持明确的本地前端来源")
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path.as_posix()}"
