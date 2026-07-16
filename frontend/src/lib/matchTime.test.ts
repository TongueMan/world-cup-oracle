import { describe, expect, it } from 'vitest';
import { formatMatchTime } from './matchTime';

describe('formatMatchTime', () => {
  it('does not present an inferred midnight as the kickoff clock', () => {
    const value = formatMatchTime({
      kickoff_label: '今天',
      kickoff_time: '2026-07-16T00:00:00+08:00',
      parse_warnings: ['kickoff_clock_time_missing'],
    });

    expect(value).not.toContain('00:00');
    expect(value).toContain('月');
  });

  it('keeps an explicitly supplied kickoff clock', () => {
    expect(formatMatchTime({
      kickoff_label: '7月16日 03:00',
      kickoff_time: '2026-07-16T03:00:00+08:00',
      parse_warnings: [],
    })).toBe('03:00');
  });
});
