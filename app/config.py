import os
from pathlib import Path


def load_env_file(env_path: str | Path | None = None) -> None:
    """
    自研轻量级 .env 自动加载器：读取项目根目录下的 .env 文件并注入到 os.environ
    无需额外安装 python-dotenv 依赖。
    """
    if env_path is None:
        # 默认定位到项目根目录下的 .env
        env_path = Path(__file__).resolve().parent.parent / ".env"

    path = Path(env_path)
    if not path.exists() or not path.is_file():
        return

    try:
        content = path.read_text(encoding="utf-8")
        for line in content.splitlines():
            line = line.strip()
            # 忽略空行与注释
            if not line or line.startswith("#"):
                continue

            if "=" in line:
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip()
                # 去除包含在两侧的引号
                if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                    val = val[1:-1]

                # 不覆盖已手动设置的环境变量
                if key and key not in os.environ:
                    os.environ[key] = val
    except Exception:
        pass


# 模块导入时自动加载 .env 变量
load_env_file()
