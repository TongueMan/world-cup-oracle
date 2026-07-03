"""YAML 配置加载器 — 从 config/ 目录加载 .yml 文件，带缓存。"""

from functools import lru_cache
from pathlib import Path

import yaml

from wcpa.shared.paths import CONFIG_DIR


@lru_cache(maxsize=32)
def load_config(name: str) -> dict:
    """从 config/{name}.yml 加载配置。结果缓存。

    Args:
        name: 配置文件名（不含扩展名），如 ``"app"`` 对应 ``config/app.yml``。

    Returns:
        解析后的字典。

    Raises:
        FileNotFoundError: 配置文件不存在。
    """
    path: Path = CONFIG_DIR / f"{name}.yml"
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_all_configs() -> dict:
    """加载 config/ 目录下所有 .yml 配置文件。

    Returns:
        ``{文件名(stem): 配置字典}`` 的字典。
    """
    configs: dict = {}
    for yml_file in CONFIG_DIR.glob("*.yml"):
        name = yml_file.stem
        configs[name] = load_config(name)
    return configs
