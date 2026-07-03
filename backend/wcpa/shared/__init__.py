"""shared 包 — 共享基础设施层。

导出项目级常量、异常、Result 类型、路径、RNG 工具和配置加载器。
"""

from wcpa.shared.constants import *  # noqa: F401, F403
from wcpa.shared.errors import *  # noqa: F401, F403
from wcpa.shared.result import Result
from wcpa.shared.paths import (
    PROJECT_ROOT,
    CONFIG_DIR,
    DATA_DIR,
    FIXTURES_DIR,
    ARTIFACTS_DIR,
    OUTPUTS_DIR,
    PREDICTIONS_DIR,
    REPORTS_DIR,
)
from wcpa.shared.random_utils import create_rng, derive_rng, spawn_children
from wcpa.shared.config_loader import load_config, load_all_configs
