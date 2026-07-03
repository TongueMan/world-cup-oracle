"""数据解析器 — MVP 桩实现。"""


class Parser:
    """解析器基类。"""

    def parse(self, raw_data) -> list:
        raise NotImplementedError("TODO: 实现数据解析")
