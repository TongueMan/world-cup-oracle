import type { WorldCupMatch } from './types';

type MatchClock = Pick<WorldCupMatch, 'kickoff_label' | 'kickoff_time' | 'parse_warnings'>;

export function formatMatchTime(match: MatchClock) {
  const normalized = normalizeRelativeKickoffLabel(match.kickoff_label);
  if (normalized) {
    const time = normalized.match(/\d{1,2}:\d{2}/)?.[0];
    if (time) return time;
  }
  if (match.parse_warnings?.includes('kickoff_clock_time_missing')) {
    return normalized || match.kickoff_label || '开球时间待定';
  }
  return formatDateTime(match.kickoff_time) || normalized || match.kickoff_label || '';
}

function normalizeRelativeKickoffLabel(label: string | null | undefined) {
  if (!label) return '';
  const relative = label.match(/^(昨天|今天|明天)(.*)$/);
  if (!relative) return label;
  const offset = relative[1] === '昨天' ? -1 : relative[1] === '明天' ? 1 : 0;
  const base = new Date();
  base.setDate(base.getDate() + offset);
  return `${formatChineseDate(base)}${relative[2] ?? ''}`;
}

function formatChineseDate(date: Date) {
  const weekdays = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
  return `${date.getMonth() + 1}月${date.getDate()}日${weekdays[date.getDay()]}`;
}

function formatDateTime(value: string | null | undefined) {
  if (!value) return '';
  try {
    return new Date(value).toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return value;
  }
}
