"""数据采集器 — MVP 桩实现。"""


class Collector:
    """采集器基类。"""

    def collect(self) -> list:
        raise NotImplementedError("TODO: 实现数据采集")
