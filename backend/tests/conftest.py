"""pytest 配置。"""

import os
import sys
from pathlib import Path

# 确保 backend 目录在 sys.path 中
BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

# 加载 .env（如果存在）
env_file = BACKEND_ROOT / ".env"
if env_file.exists():
    from dotenv import load_dotenv

    load_dotenv(env_file)