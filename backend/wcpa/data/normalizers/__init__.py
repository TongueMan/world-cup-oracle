"""数据标准化器 — MVP 桩实现。"""


class Normalizer:
    """标准化基类。"""

    def normalize(self, raw_data: list) -> list:
        raise NotImplementedError("TODO: 实现数据标准化")
