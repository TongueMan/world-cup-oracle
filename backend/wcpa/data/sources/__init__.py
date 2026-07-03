"""数据源适配器 — MVP 桩实现。"""


class SourceAdapter:
    """数据源适配器基类。"""

    def fetch(self) -> list:
        raise NotImplementedError("TODO: 实现数据源适配")
