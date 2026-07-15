import { type FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../lib/api';
import type { KeyboardEvent } from 'react';
import type {
  AgentCapabilities,
  AgentChatMessage,
  AgentLLMConfig,
  AgentPageContext,
  AgentProviderCapability,
  AgentSearchResult,
} from '../lib/types';

interface AgentDrawerProps {
  open: boolean;
  sessionKey: string;
  context: AgentPageContext;
  initialPrompt?: string;
  onClose: () => void;
}

type ViewMode = 'chat' | 'settings';
type HeaderIconName = 'settings' | 'clear' | 'close';

interface ReasoningStep {
  phase: string;
  title: string;
  summary: string;
  details?: Record<string, unknown>;
}

interface AgentSessionState {
  messages: AgentChatMessage[];
  input: string;
  sources: AgentSearchResult[];
  reasoningSteps: ReasoningStep[];
  status: string;
}

const STORAGE_KEY = 'wcpa.agent.sessionConfig';
const FALLBACK_CAPABILITIES: AgentCapabilities = {
  providers: [
    {
      id: 'deepseek',
      label: 'DeepSeek',
      base_url: 'https://api.deepseek.com',
      custom_base_url: false,
      models: [
        { id: 'deepseek-chat', label: 'DeepSeek Chat', mode: 'fast' },
        { id: 'deepseek-reasoner', label: 'DeepSeek Reasoner', mode: 'analysis' },
      ],
    },
    {
      id: 'custom',
      label: 'Custom OpenAI-compatible',
      base_url: null,
      custom_base_url: true,
      models: [],
    },
  ],
  search: { enabled: false, provider: null, message: 'Web search is not enabled.' },
};

function HeaderIcon({ name }: { name: HeaderIconName }) {
  const common = {
    'aria-hidden': true,
    fill: 'none',
    focusable: false,
    stroke: 'currentColor',
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    strokeWidth: 2,
    viewBox: '0 0 24 24',
  };

  if (name === 'settings') {
    return (
      <svg {...common}>
        <path d="M4 7h16" />
        <path d="M4 17h16" />
        <path d="M9 4v6" />
        <path d="M15 14v6" />
      </svg>
    );
  }
  if (name === 'clear') {
    return (
      <svg {...common}>
        <path d="M6 7h12" />
        <path d="M10 11v6" />
        <path d="M14 11v6" />
        <path d="M9 7l1-2h4l1 2" />
        <path d="M8 7l1 13h6l1-13" />
      </svg>
    );
  }
  return (
    <svg {...common}>
      <path d="M6 6l12 12" />
      <path d="M18 6L6 18" />
    </svg>
  );
}

export function AgentDrawer({ open, sessionKey, context, initialPrompt = '', onClose }: AgentDrawerProps) {
  const [capabilities, setCapabilities] = useState<AgentCapabilities>(FALLBACK_CAPABILITIES);
  const [config, setConfig] = useState<AgentLLMConfig>(() => loadConfig());
  const [viewMode, setViewMode] = useState<ViewMode>(config.apiKey ? 'chat' : 'settings');
  const [sessions, setSessions] = useState<Record<string, AgentSessionState>>({});
  const [streamingSessionKey, setStreamingSessionKey] = useState<string | null>(null);
  const [testing, setTesting] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const previousSessionKeyRef = useRef(sessionKey);

  const session = sessions[sessionKey] ?? emptySession(initialPrompt);
  const { messages, input, sources, reasoningSteps, status } = session;
  const streaming = streamingSessionKey === sessionKey;

  useEffect(() => {
    if (!open) return;
    api.getAgentCapabilities()
      .then((data) => {
        setCapabilities(data);
        setConfig((current) => normalizeConfig(current, data));
      })
      .catch((err) => {
        const message = err instanceof Error ? err.message : String(err);
        setSessions((current) => {
          const existing = current[sessionKey] ?? emptySession(initialPrompt);
          return { ...current, [sessionKey]: { ...existing, status: message } };
        });
      });
  }, [initialPrompt, open, sessionKey]);

  useEffect(() => {
    setSessions((current) => {
      const existing = current[sessionKey];
      if (existing) {
        if (!initialPrompt || existing.input || existing.messages.length > 0) return current;
        return { ...current, [sessionKey]: { ...existing, input: initialPrompt } };
      }
      return { ...current, [sessionKey]: emptySession(initialPrompt) };
    });
  }, [initialPrompt, sessionKey]);

  useEffect(() => {
    const previousSessionKey = previousSessionKeyRef.current;
    if (previousSessionKey !== sessionKey && streamingSessionKey === previousSessionKey) {
      abortRef.current?.abort();
      abortRef.current = null;
      setStreamingSessionKey(null);
      setSessions((current) => {
        const existing = current[previousSessionKey] ?? emptySession();
        return { ...current, [previousSessionKey]: { ...existing, status: '已停止' } };
      });
    }
    previousSessionKeyRef.current = sessionKey;
  }, [sessionKey, streamingSessionKey]);

  useEffect(() => {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(config));
  }, [config]);

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ block: 'end' });
  }, [messages, streaming, sources, reasoningSteps, status]);

  const provider = useMemo(
    () => capabilities.providers.find((item) => item.id === config.provider),
    [capabilities.providers, config.provider],
  );
  const models = provider?.models ?? [];
  const canChat = Boolean(config.provider && config.model && config.apiKey);
  const searchAllowed = capabilities.search.enabled;

  if (!open) return null;

  function updateConfig(patch: Partial<AgentLLMConfig>) {
    setConfig((current) => ({ ...current, ...patch }));
  }

  function handleProviderChange(providerId: string) {
    const nextProvider = capabilities.providers.find((item) => item.id === providerId);
    updateConfig({
      provider: providerId,
      model: nextProvider?.custom_base_url ? config.model : nextProvider?.models[0]?.id ?? '',
      baseURL: nextProvider?.custom_base_url ? config.baseURL : '',
    });
  }

  async function handleTest() {
    setTesting(true);
    updateSession(sessionKey, { status: '' });
    try {
      const result = await api.testAgentProvider(config);
      updateSession(sessionKey, { status: result.message });
    } catch (err) {
      updateSession(sessionKey, { status: err instanceof Error ? err.message : String(err) });
    } finally {
      setTesting(false);
    }
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    await sendMessage(input);
  }

  async function sendMessage(raw: string) {
    const message = raw.trim();
    if (!message || streamingSessionKey) return;
    if (!canChat) {
      setViewMode('settings');
      return;
    }

    const requestSessionKey = sessionKey;
    const requestContext = context;
    const matchAnalysis = Boolean(requestContext.currentMatchId);
    const factsOnly = wantsFactsOnly(message);
    const shouldSearch = !factsOnly && (
      config.searchEnabled
      || wantsWebSearch(message)
      || wantsPrediction(message)
      || wantsHistoricalHeadToHead(message)
      || matchAnalysis
    );
    const history = messages.slice(-10);
    updateSession(requestSessionKey, (current) => ({
      ...current,
      input: '',
      status: '',
      sources: [],
      reasoningSteps: [],
      messages: [...current.messages, { role: 'user', content: message }, { role: 'assistant', content: '' }],
    }));
    setStreamingSessionKey(requestSessionKey);
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const response = await fetch('/api/agents/research/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message,
          context: requestContext,
          history,
          llmConfig: { ...config, searchEnabled: shouldSearch },
          searchMode: shouldSearch ? 'required' : 'local_only',
          toolIntent: matchAnalysis ? 'match_analysis' : 'general',
        }),
        signal: controller.signal,
      });
      if (!response.ok || !response.body) throw new Error(await readError(response));
      await readSSE(response.body, {
        onToken: (token) => updateSession(requestSessionKey, (current) => ({ ...current, messages: appendToLastAssistant(current.messages, token) })),
        onSources: (rows) => updateSession(requestSessionKey, { sources: rows }),
        onReasoning: (step) => updateSession(requestSessionKey, (current) => ({ ...current, reasoningSteps: [...current.reasoningSteps, step] })),
        onProgress: (message) => updateSession(requestSessionKey, { status: message }),
        onError: (message) => updateSession(requestSessionKey, { status: message }),
        onDone: (payload) => {
          if (typeof payload.answer === 'string') {
            updateSession(requestSessionKey, (current) => ({ ...current, messages: replaceLastAssistant(current.messages, payload.answer as string) }));
          }
          const diagnostics = payload.diagnostics as { searchedCount?: number; adoptedCount?: number; filteredCount?: number } | undefined;
          if (diagnostics?.searchedCount != null) {
            updateSession(requestSessionKey, { status: `完成：检索 ${diagnostics.searchedCount} 条，采用 ${diagnostics.adoptedCount ?? 0} 条，过滤 ${diagnostics.filteredCount ?? 0} 条。` });
          } else {
            updateSession(requestSessionKey, { status: '完成' });
          }
        },
      });
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        const text = err instanceof Error ? err.message : String(err);
        updateSession(requestSessionKey, (current) => ({
          ...current,
          status: text,
          messages: replaceLastAssistant(current.messages, text),
        }));
      }
    } finally {
      setStreamingSessionKey((current) => current === requestSessionKey ? null : current);
      abortRef.current = null;
    }
  }

  function stopStream() {
    abortRef.current?.abort();
    abortRef.current = null;
    if (streamingSessionKey) updateSession(streamingSessionKey, { status: '已停止' });
    setStreamingSessionKey(null);
  }

  function clearChat() {
    updateSession(sessionKey, emptySession(initialPrompt));
  }

  function setInput(value: string) {
    updateSession(sessionKey, { input: value });
  }

  function handleInputKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing) return;
    event.preventDefault();
    void sendMessage(input);
  }

  function updateSession(
    key: string,
    patch: Partial<AgentSessionState> | ((current: AgentSessionState) => AgentSessionState),
  ) {
    setSessions((current) => {
      const existing = current[key] ?? emptySession(key === sessionKey ? initialPrompt : '');
      const next = typeof patch === 'function' ? patch(existing) : { ...existing, ...patch };
      return { ...current, [key]: next };
    });
  }

  return (
    <div className="agent-shell" role="dialog" aria-modal="true" aria-label="World Cup Agent">
      <div className="agent-backdrop" onClick={onClose} />
      <aside className="agent-drawer wide">
        <header className="agent-header">
          <div className="agent-title-block min-w-0">
            <div className="text-sm font-black text-white">世界杯预测助手</div>
            <div className="truncate text-xs text-white/55">{context.summary || '围绕当前页面回答问题'}</div>
          </div>
          <div className="agent-header-actions flex items-center gap-2">
            <button type="button" className="agent-icon-btn agent-icon-btn--settings" onClick={() => setViewMode(viewMode === 'chat' ? 'settings' : 'chat')} title="设置" aria-label="设置">
              <HeaderIcon name="settings" />
            </button>
            <button type="button" className="agent-icon-btn agent-icon-btn--danger" onClick={clearChat} title="清空" aria-label="清空">
              <HeaderIcon name="clear" />
            </button>
            <button type="button" className="agent-icon-btn agent-icon-btn--close" onClick={onClose} title="关闭" aria-label="关闭">
              <HeaderIcon name="close" />
            </button>
          </div>
        </header>

        {viewMode === 'settings' ? (
          <AgentSettings
            capabilities={capabilities}
            config={config}
            provider={provider}
            models={models}
            searchDisabled={!capabilities.search.enabled}
            status={status}
            testing={testing}
            onProviderChange={handleProviderChange}
            onConfigChange={updateConfig}
            onTest={handleTest}
            onStart={() => setViewMode('chat')}
          />
        ) : (
          <div className="agent-chat">
            {!canChat && (
              <div className="agent-warning">
                请先配置模型 API Key。
                <button type="button" onClick={() => setViewMode('settings')}>去配置</button>
              </div>
            )}
            <div className="agent-quick-row">
              <button type="button" disabled={streaming} onClick={() => void sendMessage('分析当前页面')}>分析当前页面</button>
              <button type="button" disabled={streaming || !searchAllowed} onClick={() => void sendMessage('查找最新新闻并给出判断')}>最新新闻</button>
              <button type="button" disabled={streaming} onClick={() => void sendMessage('用确定事实回答，不要编造')}>确定事实</button>
            </div>

            <div className="agent-messages">
              {messages.length === 0 && <div className="agent-empty">可以询问赛程、球队、新闻、场馆环境或预测依据。</div>}
              {messages.map((message, index) => {
                const isActiveAssistant = message.role === 'assistant' && index === messages.length - 1;
                return (
                  <div key={`${message.role}-${index}`} className={`agent-message ${message.role}`}>
                    <div>
                      {isActiveAssistant && reasoningSteps.length > 0 && <ReasoningPanel steps={reasoningSteps} streaming={streaming} />}
                      <RichText content={message.content || (streaming && index === messages.length - 1 ? '正在生成...' : '')} />
                    </div>
                  </div>
                );
              })}
              {sources.length > 0 && <SourceList sources={sources} />}
              {status && <div className="agent-status">{status}</div>}
              <div ref={scrollRef} />
            </div>

            <form className="agent-input" onSubmit={handleSubmit}>
              <textarea
                value={input}
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={handleInputKeyDown}
                placeholder="输入你的问题..."
                rows={3}
              />
              <div className="agent-input-actions">
                {streaming ? (
                  <button type="button" onClick={stopStream}>停止</button>
                ) : (
                  <button type="submit" disabled={!input.trim() || !canChat}>发送</button>
                )}
              </div>
              <div className="agent-search-note">
                {!capabilities.search.enabled
                  ? capabilities.search.message
                  : config.searchEnabled
                    ? '本次对话允许联网搜索'
                    : context.currentMatchId
                      ? '比赛分析默认联网优先'
                      : '当前仅使用本地数据'}
              </div>
            </form>
          </div>
        )}
      </aside>
    </div>
  );
}

function AgentSettings({
  capabilities,
  config,
  provider,
  models,
  searchDisabled,
  status,
  testing,
  onProviderChange,
  onConfigChange,
  onTest,
  onStart,
}: {
  capabilities: AgentCapabilities;
  config: AgentLLMConfig;
  provider?: AgentProviderCapability;
  models: AgentProviderCapability['models'];
  searchDisabled: boolean;
  status: string;
  testing: boolean;
  onProviderChange: (provider: string) => void;
  onConfigChange: (patch: Partial<AgentLLMConfig>) => void;
  onTest: () => void;
  onStart: () => void;
}) {
  return (
    <div className="agent-settings">
      <div>
        <label>模型服务商</label>
        <select value={config.provider} onChange={(event) => onProviderChange(event.target.value)}>
          {capabilities.providers.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
        </select>
      </div>
      {provider?.custom_base_url && (
        <div>
          <label>Base URL</label>
          <input value={config.baseURL ?? ''} onChange={(event) => onConfigChange({ baseURL: event.target.value })} placeholder="https://api.example.com/v1" />
        </div>
      )}
      <div>
        <label>模型</label>
        {provider?.custom_base_url ? (
          <input value={config.model} onChange={(event) => onConfigChange({ model: event.target.value })} placeholder="model-name" />
        ) : (
          <select value={config.model} onChange={(event) => onConfigChange({ model: event.target.value })}>
            {models.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
          </select>
        )}
      </div>
      <div>
        <label>API Key</label>
        <input type="password" value={config.apiKey} onChange={(event) => onConfigChange({ apiKey: event.target.value })} placeholder="sk-..." autoComplete="off" />
      </div>
      <label className={searchDisabled ? 'agent-check muted' : 'agent-check'}>
        <input type="checkbox" checked={config.searchEnabled} disabled={searchDisabled} onChange={(event) => onConfigChange({ searchEnabled: event.target.checked })} />
        联网搜索
      </label>
      <p className="agent-help">{searchDisabled ? capabilities.search.message : 'API Key 只保存在当前浏览器会话中。'}</p>
      {status && <div className="agent-status">{status}</div>}
      <div className="agent-settings-actions">
        <button type="button" onClick={onTest} disabled={testing || !config.apiKey}>{testing ? '测试中...' : '测试连接'}</button>
        <button type="button" onClick={onStart} disabled={!config.apiKey || !config.model}>开始使用</button>
      </div>
    </div>
  );
}

function SourceList({ sources }: { sources: AgentSearchResult[] }) {
  return (
    <div className="agent-sources">
      <div className="mb-2 text-xs font-black text-white/70">联网来源</div>
      {sources.slice(0, 8).map((source, index) => (
        <a key={source.url || index} href={source.url} target="_blank" rel="noreferrer">
          <span>{source.citationId ? `[${source.citationId}] ` : `[${index + 1}] `}{source.title}</span>
          <small>{[source.sourceType, source.domain || source.source, source.publishedAt].filter(Boolean).join(' · ')}</small>
        </a>
      ))}
    </div>
  );
}

function ReasoningPanel({ steps, streaming }: { steps: ReasoningStep[]; streaming: boolean }) {
  const visible = steps.slice(-6);
  return (
    <details className="agent-reasoning" open>
      <summary>
        推理过程
        {streaming ? <span>分析中</span> : <span>已完成</span>}
      </summary>
      <ol>
        {visible.map((step, index) => (
          <li key={`${step.phase}-${index}`}>
            <strong>{step.title}</strong>
            <p>{step.summary}</p>
          </li>
        ))}
      </ol>
    </details>
  );
}

function RichText({ content }: { content: string }) {
  const lines = content.replace(/https?:\/\/\S+/g, '').split('\n');
  return <>{lines.map((line, index) => line.trim() ? <p key={index}>{renderInline(line)}</p> : <br key={index} />)}</>;
}

function renderInline(text: string) {
  const parts = text.split(/(\*\*[^*]+\*\*|\[[0-9]+\])/g).filter(Boolean);
  return parts.map((part, index) => {
    const bold = part.match(/^\*\*([^*]+)\*\*$/);
    if (bold) return <strong key={index}>{bold[1]}</strong>;
    if (/^\[[0-9]+\]$/.test(part)) return <sup key={index}>{part}</sup>;
    return <span key={index}>{part}</span>;
  });
}

function appendToLastAssistant(messages: AgentChatMessage[], token: string) {
  const next = [...messages];
  const last = next[next.length - 1];
  if (last?.role === 'assistant') next[next.length - 1] = { ...last, content: last.content + token };
  return next;
}

function replaceLastAssistant(messages: AgentChatMessage[], content: string) {
  const next = [...messages];
  const last = next[next.length - 1];
  if (last?.role === 'assistant') next[next.length - 1] = { ...last, content };
  else next.push({ role: 'assistant', content });
  return next;
}

function emptySession(input = ''): AgentSessionState {
  return {
    messages: [],
    input,
    sources: [],
    reasoningSteps: [],
    status: '',
  };
}

function defaultConfig(): AgentLLMConfig {
  return { provider: 'deepseek', model: 'deepseek-chat', apiKey: '', baseURL: '', searchEnabled: false };
}

function loadConfig(): AgentLLMConfig {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (raw) return { ...defaultConfig(), ...JSON.parse(raw) };
  } catch {
    // ignore broken session data
  }
  return defaultConfig();
}

function normalizeConfig(config: AgentLLMConfig, capabilities: AgentCapabilities): AgentLLMConfig {
  const provider = capabilities.providers.find((item) => item.id === config.provider) ?? capabilities.providers[0];
  if (!provider) return config;
  const model = provider.custom_base_url
    ? config.model
    : provider.models.some((item) => item.id === config.model)
      ? config.model
      : provider.models[0]?.id ?? '';
  return { ...config, provider: provider.id, model };
}

function wantsWebSearch(message: string) {
  return /(联网|网上|搜索|查找|检索|web search|search online|google|firecrawl)/i.test(message);
}

function wantsPrediction(message: string) {
  return /(预测|预估|看好|冠军|夺冠|胜负|比分|概率|可能|倾向|predict|prediction|champion|winner|odds|favorite)/i.test(message);
}

function wantsHistoricalHeadToHead(message: string) {
  return /(历史|历史上|此前|交手|交锋|对战|往绩|head to head|h2h|previous meetings|past meetings)/i.test(message)
    && /(结果|比分|战绩|记录|results|record)/i.test(message);
}

function wantsFactsOnly(message: string) {
  return /(确定事实|只说事实|不要预测|不要分析|facts only|known facts)/i.test(message);
}

async function readError(response: Response) {
  try {
    const payload = await response.json();
    return typeof payload.detail === 'string' ? payload.detail : JSON.stringify(payload.detail ?? payload);
  } catch {
    return `${response.status} ${response.statusText}`;
  }
}

async function readSSE(
  body: ReadableStream<Uint8Array>,
  handlers: {
    onToken: (token: string) => void;
    onSources: (rows: AgentSearchResult[]) => void;
    onReasoning: (step: ReasoningStep) => void;
    onProgress: (message: string) => void;
    onError: (message: string) => void;
    onDone: (payload: Record<string, unknown>) => void;
  },
) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split('\n\n');
    buffer = chunks.pop() ?? '';
    for (const chunk of chunks) handleSSEChunk(chunk, handlers);
  }
  if (buffer.trim()) handleSSEChunk(buffer, handlers);
}

function handleSSEChunk(
  chunk: string,
  handlers: {
    onToken: (token: string) => void;
    onSources: (rows: AgentSearchResult[]) => void;
    onReasoning: (step: ReasoningStep) => void;
    onProgress: (message: string) => void;
    onError: (message: string) => void;
    onDone: (payload: Record<string, unknown>) => void;
  },
) {
  const event = chunk.match(/^event:\s*(.+)$/m)?.[1]?.trim();
  const dataLine = chunk.match(/^data:\s*(.+)$/m)?.[1];
  if (!event || !dataLine) return;
  let payload: Record<string, unknown>;
  try {
    payload = JSON.parse(dataLine);
  } catch {
    return;
  }
  if (event === 'token') handlers.onToken(String(payload.content ?? ''));
  else if (event === 'sources' || event === 'search_results') handlers.onSources((payload.results as AgentSearchResult[]) ?? []);
  else if (event === 'reasoning') handlers.onReasoning(normalizeReasoningStep(payload));
  else if (event === 'progress' || event === 'search_warning') handlers.onProgress(String(payload.message ?? event));
  else if (event === 'query_plan') handlers.onProgress('已生成检索计划');
  else if (event === 'evidence_ready') handlers.onProgress('证据已就绪，正在生成回答');
  else if (event === 'quality_check') handlers.onProgress('正在校验回答质量');
  else if (event === 'error') handlers.onError(String(payload.message ?? 'Agent request failed.'));
  else if (event === 'done') handlers.onDone(payload);
}

function normalizeReasoningStep(payload: Record<string, unknown>): ReasoningStep {
  return {
    phase: String(payload.phase ?? 'step'),
    title: String(payload.title ?? '分析步骤'),
    summary: String(payload.summary ?? ''),
    details: typeof payload.details === 'object' && payload.details !== null
      ? payload.details as Record<string, unknown>
      : undefined,
  };
}
