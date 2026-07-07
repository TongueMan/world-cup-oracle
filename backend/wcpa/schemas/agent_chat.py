"""Schemas for interactive Agent chat."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentProviderModel(BaseModel):
    id: str
    label: str
    mode: str = "balanced"


class AgentProviderCapability(BaseModel):
    id: str
    label: str
    base_url: str | None = None
    custom_base_url: bool = False
    models: list[AgentProviderModel]


class AgentSearchCapability(BaseModel):
    enabled: bool
    provider: str | None = None
    message: str


class AgentCapabilitiesResponse(BaseModel):
    providers: list[AgentProviderCapability]
    search: AgentSearchCapability


class AgentLLMConfig(BaseModel):
    provider: str
    model: str
    api_key: str = Field(default="", alias="apiKey")
    base_url: str | None = Field(default=None, alias="baseURL")
    search_enabled: bool = Field(default=False, alias="searchEnabled")


class AgentChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class AgentPageContext(BaseModel):
    current_page: str | None = Field(default=None, alias="currentPage")
    active_tab: str | None = Field(default=None, alias="activeTab")
    current_match_id: str | None = Field(default=None, alias="currentMatchId")
    selected_date: str | None = Field(default=None, alias="selectedDate")
    summary: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class AgentChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    context: AgentPageContext = Field(default_factory=AgentPageContext)
    history: list[AgentChatMessage] = Field(default_factory=list, max_length=20)
    llm_config: AgentLLMConfig = Field(alias="llmConfig")


class AgentResearchRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    context: AgentPageContext = Field(default_factory=AgentPageContext)
    history: list[AgentChatMessage] = Field(default_factory=list, max_length=20)
    llm_config: AgentLLMConfig = Field(alias="llmConfig")
    search_mode: Literal["auto", "required", "local_only"] = Field(default="auto", alias="searchMode")
    tool_intent: Literal[
        "match_analysis",
        "pre_match_report",
        "post_match_report",
        "previous_match_report",
        "latest_news",
        "weather_environment",
        "general",
    ] = Field(default="general", alias="toolIntent")


class AgentProviderTestRequest(BaseModel):
    llm_config: AgentLLMConfig = Field(alias="llmConfig")


class AgentProviderTestResponse(BaseModel):
    ok: bool
    message: str


class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str = ""
    source: str
    domain: str = ""
    published_at: str | None = Field(default=None, alias="publishedAt")
    source_quality_score: float = Field(default=0, alias="sourceQualityScore")
    relevance_score: float = Field(default=0, alias="relevanceScore")
    source_type: str = Field(default="media", alias="sourceType")
    adoption_reason: str = Field(default="", alias="adoptionReason")
    citation_id: int | None = Field(default=None, alias="citationId")
    excerpt: str = ""


class AgentMatchToolRequest(BaseModel):
    llm_config: AgentLLMConfig | None = Field(default=None, alias="llmConfig")
    question: str = ""


class AgentEvidenceSource(BaseModel):
    title: str
    url: str
    domain: str = ""
    snippet: str = ""
    source: str
    published_at: str | None = Field(default=None, alias="publishedAt")
    source_quality_score: float = Field(default=0, alias="sourceQualityScore")
    relevance_score: float = Field(default=0, alias="relevanceScore")
    source_type: str = Field(default="media", alias="sourceType")
    adoption_reason: str = Field(default="", alias="adoptionReason")
    citation_id: int | None = Field(default=None, alias="citationId")
    excerpt: str = ""


class AgentMatchConfirmation(BaseModel):
    current_match: dict[str, Any] = Field(default_factory=dict, alias="currentMatch")
    requested_teams: list[str] = Field(default_factory=list, alias="requestedTeams")
    candidates: list[dict[str, Any]] = Field(default_factory=list)


class AgentDiagnostics(BaseModel):
    run_id: str | None = Field(default=None, alias="runId")
    query_plan: dict[str, Any] = Field(default_factory=dict, alias="queryPlan")
    searched_count: int = Field(default=0, alias="searchedCount")
    adopted_count: int = Field(default=0, alias="adoptedCount")
    filtered_count: int = Field(default=0, alias="filteredCount")
    filtered_sources: list[dict[str, Any]] = Field(default_factory=list, alias="filteredSources")


class AgentMatchToolResponse(BaseModel):
    answer: str
    sources: list[AgentEvidenceSource]
    run_id: str | None = None
    status: str = "ok"
    confirmation: AgentMatchConfirmation | None = None
    diagnostics: AgentDiagnostics | None = None
    progress: list[str] = Field(default_factory=list)
    used_search: bool
    search_allowed: bool
    search_intents: list[str]
    missing_local_fields: list[str]
    evidence_status: str
