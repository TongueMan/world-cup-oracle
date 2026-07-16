import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { completionStatusText, resolveToolIntent } from '../lib/agentResearch';
import { ReasoningPanel } from './AgentDrawer';

describe('AgentDrawer research behavior', () => {
  it('uses a post-match report intent for completed matches', () => {
    expect(resolveToolIntent({ currentMatchId: 'eng-arg', data: { status: 'complete' } })).toBe('post_match_report');
    expect(resolveToolIntent({ currentMatchId: 'eng-arg', data: { status: 'scheduled' } })).toBe('match_analysis');
    expect(resolveToolIntent({ currentPage: 'worldcup-dashboard' })).toBe('general');
  });

  it('does not describe a source-free post-match answer as successfully researched', () => {
    const text = completionStatusText({
      status: 'evidence_unavailable',
      diagnostics: { intent: 'post_match_report', adoptedCount: 0, searchError: '联网查询超时。' },
    });

    expect(text).toContain('未取得可用战报');
    expect(text).toContain('本地确定事实');
    expect(text).toContain('联网查询超时');
  });

  it('keeps developer reasoning collapsed by default', () => {
    render(
      <ReasoningPanel
        steps={[{ phase: 'plan', title: '拆解问题', summary: '识别赛后复盘意图。' }]}
        streaming={false}
      />,
    );

    expect(screen.getByText('推理过程').closest('details')).not.toHaveAttribute('open');
  });
});
