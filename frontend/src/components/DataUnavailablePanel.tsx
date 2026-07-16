import type { DataQualityReport, DataSourceStatus } from '../lib/types';

interface DataUnavailablePanelProps {
  status: DataQualityReport | null;
  error?: string | null;
}

const BING_RULES = ['Bing Sports 单源', '原始快照留存', '字段不足不预测', '不补假赛果'];

export function DataUnavailablePanel({ status, error }: DataUnavailablePanelProps) {
  const manifest = status?.knowledge_manifest;
  const counts = manifest?.counts ?? {};
  const sourceSummary = summarizeSources(status?.source_statuses ?? []);
  const invalidRecords = status?.invalid_records ?? [];
  const missingFields = summarizeInvalidFields(invalidRecords);
  const primaryMessage =
    status?.message ??
    error ??
    '后端尚未返回 Bing 知识库状态。请确认 API 服务可访问后重新同步。';

  return (
    <section className="space-y-5">
      <div className="oracle-panel field-panel relative overflow-hidden p-5 sm:p-7">
        <div className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr] lg:items-end">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.34em] text-[#ffe18a]">
              Bing Knowledge Gate
            </p>
            <h2 className="mt-3 max-w-3xl text-3xl font-black tracking-wide text-white sm:text-4xl">
              Bing 单源采集中，知识库完整前不生成预测
            </h2>
            <p className="mt-4 max-w-3xl text-sm leading-7 text-white/74">
              {primaryMessage}
              当前正式数据入口只接受 Bing Sports 世界杯页面。比赛、赛程表、资讯、排名、统计信息会先落成知识库；
              如果字段不足，页面停在这里，而不是生成模拟冠军或无依据结论。
            </p>
          </div>

          <div className="rounded-3xl border border-white/16 bg-black/28 p-4 backdrop-blur">
            <div className="flex items-center justify-between gap-3">
              <span className="text-sm font-medium text-white/68">预测放行状态</span>
              <span className="rounded-full border border-[#ffe18a]/45 bg-[#ffe18a]/12 px-3 py-1 text-xs font-bold text-[#ffe18a]">
                等待 Bing 结构化数据
              </span>
            </div>
            <div className="mt-4 grid grid-cols-2 gap-2">
              {BING_RULES.map((rule) => (
                <span
                  key={rule}
                  className="rounded-xl border border-white/12 bg-white/8 px-3 py-2 text-xs text-white/72"
                >
                  {rule}
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <StatusTile
          eyebrow="Matches"
          title="比赛与赛果"
          tone={(counts.matches ?? sourceSummary.totalRecords) > 0 ? 'warm' : 'blocked'}
          metric={`${counts.matches ?? sourceSummary.totalRecords} 场`}
          description="从 Bing 比赛 tab 和分页接口提取赛程卡片、比分、状态、阶段、小组和详情链接。"
        />
        <StatusTile
          eyebrow="Bracket / Table"
          title="淘汰赛与排名"
          tone={(counts.bracket ?? 0) + (counts.standings ?? 0) > 0 ? 'warm' : 'blocked'}
          metric={`${(counts.bracket ?? 0) + (counts.standings ?? 0)} 条`}
          description="赛程表 tab 负责淘汰赛树，排名 tab 负责小组积分榜；占位符不会进入真实球队表。"
        />
        <StatusTile
          eyebrow="News / Stats"
          title="资讯与球员统计"
          tone={(counts.news ?? 0) + (counts.player_stats ?? 0) > 0 ? 'warm' : 'idle'}
          metric={`${(counts.news ?? 0) + (counts.player_stats ?? 0)} 条`}
          description="资讯和统计信息进入知识库，供之后 Agent 检索和解释，不作为伪造球队数据。"
        />
      </div>

      <div className="oracle-panel grid gap-5 p-5 lg:grid-cols-[0.95fr_1.05fr]">
        <div>
          <div className="mb-3 flex items-center justify-between gap-3">
            <h3 className="text-base font-semibold text-white">Bing 采集雷达</h3>
            <span className="text-xs text-white/42">单源优先 · 原始快照可追溯</span>
          </div>
          <div className="space-y-3">
            {(status?.source_statuses ?? []).length === 0 ? (
              <EmptyLine text="暂无 Bing 采集报告，请先运行知识库同步。" />
            ) : (
              status?.source_statuses.map((source) => (
                <SourceRow key={source.source_key} source={source} />
              ))
            )}
          </div>
        </div>

        <div>
          <div className="mb-3 flex items-center justify-between gap-3">
            <h3 className="text-base font-semibold text-white">为什么还不能预测</h3>
            <span className="text-xs text-white/42">只展示前 12 条审计线索</span>
          </div>
          <div className="max-h-72 space-y-3 overflow-auto pr-1">
            {(status?.missing ?? []).map((item) => (
              <AuditRow key={item} label="缺失项" value={item} />
            ))}
            {missingFields.map((item) => (
              <AuditRow key={item} label="字段缺失" value={item} />
            ))}
            {invalidRecords.slice(0, 12).map((record, index) => (
              <AuditRow
                key={`${String(record.id ?? record.dataset ?? index)}-${index}`}
                label={String(record.dataset ?? 'invalid')}
                value={formatInvalidRecord(record)}
              />
            ))}
            {(status?.missing ?? []).length === 0 && missingFields.length === 0 && invalidRecords.length === 0 && (
              <EmptyLine text="暂无具体缺口。若知识库未落盘，请先运行后端同步脚本生成 Bing manifest。" />
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

function StatusTile({
  eyebrow,
  title,
  tone,
  metric,
  description,
}: {
  eyebrow: string;
  title: string;
  tone: 'warm' | 'blocked' | 'idle';
  metric: string;
  description: string;
}) {
  const toneClass =
    tone === 'blocked'
      ? 'border-amber-200/35 bg-amber-300/12 text-amber-50'
      : tone === 'warm'
        ? 'border-emerald-200/35 bg-emerald-300/14 text-emerald-50'
        : 'border-white/20 bg-white/8 text-white/70';

  return (
    <div className="rounded-3xl border border-white/12 bg-black/22 p-5 shadow-[0_20px_45px_rgba(0,0,0,0.2)] backdrop-blur">
      <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-[#ffe18a]">{eyebrow}</p>
      <div className="mt-4 flex items-start justify-between gap-4">
        <div>
          <h3 className="text-lg font-bold text-white">{title}</h3>
          <p className="mt-2 text-sm leading-6 text-white/58">{description}</p>
        </div>
        <span className={`shrink-0 rounded-xl border px-3 py-2 text-sm font-bold ${toneClass}`}>
          {metric}
        </span>
      </div>
    </div>
  );
}

function SourceRow({ source }: { source: DataSourceStatus }) {
  const statusClass =
    source.status === 'ok'
      ? 'border-emerald-200/35 bg-emerald-300/14 text-emerald-50'
      : source.status === 'error'
        ? 'border-rose-200/35 bg-rose-300/14 text-rose-50'
        : 'border-white/20 bg-white/8 text-white/60';

  return (
    <div className="rounded-2xl border border-white/12 bg-[#08210f]/70 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-semibold text-white">{source.source_key}</span>
        <span className={`rounded-full border px-2.5 py-1 text-xs ${statusClass}`}>{source.status}</span>
      </div>
      <p className="mt-2 text-sm leading-6 text-white/58">{source.message}</p>
      <div className="mt-3 flex flex-wrap gap-2 text-xs text-white/42">
        <span>{source.records} records</span>
        <span>credibility {source.credibility}</span>
        <span>{source.fetched_at ? new Date(source.fetched_at).toLocaleString('zh-CN') : '未记录时间'}</span>
      </div>
    </div>
  );
}

function AuditRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-white/12 bg-black/24 p-3">
      <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-[#ffe18a]">{label}</div>
      <div className="mt-1 text-sm leading-6 text-white/72">{value}</div>
    </div>
  );
}

function EmptyLine({ text }: { text: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-white/18 bg-white/6 p-4 text-sm text-white/45">
      {text}
    </div>
  );
}

function summarizeSources(sources: DataSourceStatus[]) {
  return {
    totalRecords: sources.reduce((sum, source) => sum + (source.records || 0), 0),
  };
}

function summarizeInvalidFields(records: Array<Record<string, unknown>>) {
  const fields = new Set<string>();
  records.forEach((record) => {
    const rawFields = record.fields;
    if (Array.isArray(rawFields)) {
      rawFields.forEach((field) => fields.add(String(field)));
    }
  });
  return Array.from(fields).slice(0, 18);
}

function formatInvalidRecord(record: Record<string, unknown>) {
  const id = record.id ? `#${String(record.id)}` : '';
  const reason = record.reason ? String(record.reason) : '校验未通过';
  const fields = Array.isArray(record.fields) ? ` · ${record.fields.slice(0, 5).join(', ')}` : '';
  return `${id} ${reason}${fields}`.trim();
}
