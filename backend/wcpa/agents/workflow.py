"""Agent 工作流编排 — MVP 桩。"""
from __future__ import annotations
from typing import Protocol

class PipelineAgent(Protocol):
    """工程流水线 Agent 接口。"""
    def execute(self, *args, **kwargs):
        ...

class AnalysisAgent(Protocol):
    """分析人格 Agent 接口。"""
    def analyze(self, *args, **kwargs):
        ...

class Workflow:
    """Agent 工作流编排器 — MVP: pass-through。"""
    
    def __init__(self):
        # 7 个流水线 Agent
        self.data_collector = None  # TODO
        self.normalizer = None     # TODO
        self.feature_builder = None  # TODO
        self.match_predictor = None  # TODO
        self.tournament_simulator = None  # TODO
        self.reasoning_writer = None  # TODO
        self.viz_builder = None      # TODO
        
        # 7 个分析 Agent
        self.data_analyst = None     # TODO
        self.tactical_analyst = None # TODO
        self.narrative_agent = None  # TODO
        self.tarot_agent = None      # TODO
        self.iching_agent = None     # TODO
        self.astrology_agent = None  # TODO
        self.judge_agent = None      # TODO
