"""统一 seedable RNG 工具。

红线: 随机数不得散落在业务函数中，必须通过本模块创建/派生。
"""

import hashlib
from typing import Union

import numpy as np


def create_rng(seed: Union[int, None] = None) -> np.random.Generator:
    """创建 seedable random Generator。

    使用 numpy default_rng (PCG64) 引擎。
    """
    return np.random.default_rng(seed)


def derive_rng(rng: np.random.Generator, namespace: str) -> np.random.Generator:
    """从父 RNG 派生命名子 RNG。

    确保不同模块使用独立随机流但整体可复现。
    将父 rng 的 bit generator 的 state 与 namespace 混合派生新的独立随机流。

    使用 SHA-256 派生 namespace hash，确保跨进程严格可复现。
    """
    parent_seed = int(rng.integers(0, 2**31))
    namespace_hash = int.from_bytes(
        hashlib.sha256(namespace.encode("utf-8")).digest()[:8],
        "big",
    ) & 0xFFFFFFFF
    combined_seed = (parent_seed ^ namespace_hash) & 0x7FFFFFFF
    return np.random.default_rng(combined_seed)


def spawn_children(rng: np.random.Generator, n: int) -> list:
    """生成 n 个统计独立的子 RNG（用于并行模拟）。

    返回 list[np.random.Generator]。
    """
    seeds = rng.integers(0, 2**31, size=n)
    return [np.random.default_rng(int(s)) for s in seeds]
