import type { AgentPageContext } from './types';

export type AgentToolIntent = 'match_analysis' | 'post_match_report' | 'general';

export function resolveToolIntent(context: AgentPageContext): AgentToolIntent {
  if (!context.currentMatchId) return 'general';
  const status = String(context.data?.status ?? '').toLowerCase();
  if (['complete', 'completed', 'final', 'closed'].includes(status)) return 'post_match_report';
  return 'match_analysis';
}

export function completionStatusText(payload: Record<string, unknown>) {
  const status = String(payload.status ?? 'ok');
  const diagnostics = payload.diagnostics as {
    intent?: string;
    searchedCount?: number;
    adoptedCount?: number;
    filteredCount?: number;
    searchError?: string;
    quality?: { passed?: boolean; issues?: string[] };
  } | undefined;
  const adopted = diagnostics?.adoptedCount ?? 0;
  const filtered = diagnostics?.filteredCount ?? 0;
  const searchError = diagnostics?.searchError?.trim();

  if (status === 'evidence_unavailable') {
    const evidenceName = diagnostics?.intent === 'post_match_report' ? '战报' : '联网证据';
    return searchError
      ? `联网检索未取得可用${evidenceName}，当前回答只保留本地确定事实。${searchError}`
      : `联网检索未取得可用${evidenceName}，当前回答只保留本地确定事实。`;
  }
  if (status === 'quality_warning') {
    const issue = diagnostics?.quality?.issues?.[0];
    return issue ? `回答已生成，但质量校验仍有问题：${issue}` : '回答已生成，但质量校验未完全通过。';
  }
  if (adopted > 0) {
    const partial = searchError ? '；部分查询失败，但已保留成功来源' : '';
    return `已完成：采用 ${adopted} 条联网来源${filtered > 0 ? `，过滤 ${filtered} 条` : ''}${partial}。`;
  }
  if (diagnostics?.searchedCount === 0) return '已完成：本次仅使用本地确定数据。';
  return '已完成。';
}
