"""项目统一异常体系。"""


class WCPAError(Exception):
    """Base error for all WCPA errors."""

    pass


class DataQualityError(WCPAError):
    """数据质量不达标时抛出。"""

    pass


class PredictionError(WCPAError):
    """预测流程出错时抛出。"""

    pass


class SimulationError(WCPAError):
    """蒙特卡洛模拟出错时抛出。"""

    pass


class ConfigError(WCPAError):
    """配置加载或校验出错时抛出。"""

    pass


class FixtureLoadError(WCPAError):
    """赛程数据加载失败时抛出。"""

    pass
