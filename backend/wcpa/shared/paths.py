"""项目路径解析 — 从包位置向上查找项目根。"""

from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def _find_project_root() -> Path:
    """从当前包位置向上查找项目根（包含 config/ 目录的目录）。

    查找顺序:
      1. 当前文件所在目录逐级向上，找到第一个包含 config/ 子目录的目录。
      2. 若找不到，回退到上四级目录
         (wcpa/shared/paths.py → wcpa/shared → wcpa → backend → 项目根)。
    """
    current = Path(__file__).resolve()
    for parent in [current] + list(current.parents):
        if (parent / "config").is_dir():
            return parent
    # 回退: wcpa/shared/paths.py 的 parents[3] 即项目根
    return current.parents[3]


PROJECT_ROOT: Path = _find_project_root()
CONFIG_DIR: Path = PROJECT_ROOT / "config"
DATA_DIR: Path = PROJECT_ROOT / "data"
DOCS_DIR: Path = PROJECT_ROOT / "docs"
FIXTURES_DIR: Path = DATA_DIR / "fixtures"
RAW_DIR: Path = DATA_DIR / "raw"
NORMALIZED_DIR: Path = DATA_DIR / "normalized"
CACHE_DIR: Path = DATA_DIR / "cache"
ARTIFACTS_DIR: Path = DATA_DIR / "artifacts"
OUTPUTS_DIR: Path = PROJECT_ROOT / "outputs"
PREDICTIONS_DIR: Path = OUTPUTS_DIR / "predictions"
REPORTS_DIR: Path = OUTPUTS_DIR / "reports"
