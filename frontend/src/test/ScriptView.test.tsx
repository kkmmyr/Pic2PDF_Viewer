/**
 * ScriptView: セグメント区切り挿入・v1 フラット表示（B-28）。
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import ScriptView, { ChecksBadge } from '@/components/novel_db/script-view';
import type { DiscussionTurn } from '@/features/novel_db/types';

const SEGMENTS: Record<string, string> = {
    op_hook: 'OPフック',
    theme1: 'テーマ1',
};

const V2_TURNS: DiscussionTurn[] = [
    { speaker: 'A', text: 'つかみ', segment: 'op_hook' },
    { speaker: 'B', text: '返し', segment: 'op_hook' },
    { speaker: 'A', text: '本題', segment: 'theme1' },
];

describe('ScriptView', () => {
    it('segment が変わる位置にのみ区切り見出しを挿入する', () => {
        render(<ScriptView turns={V2_TURNS} segments={SEGMENTS} />);
        const separators = screen.getAllByRole('separator');
        expect(separators).toHaveLength(2);
        expect(screen.getByText('OPフック')).toBeInTheDocument();
        expect(screen.getByText('テーマ1')).toBeInTheDocument();
    });

    it('話者名はデフォルトでレイ / ミオ', () => {
        render(<ScriptView turns={V2_TURNS} segments={SEGMENTS} />);
        expect(screen.getAllByText('レイ').length).toBeGreaterThan(0);
        expect(screen.getAllByText('ミオ').length).toBeGreaterThan(0);
    });

    it('nameA / nameB で話者名を上書きできる（v1 履歴のペルソナ表示）', () => {
        render(<ScriptView turns={V2_TURNS} segments={SEGMENTS} nameA="批評家" nameB="ファン" />);
        expect(screen.getAllByText('批評家').length).toBeGreaterThan(0);
        expect(screen.getAllByText('ファン').length).toBeGreaterThan(0);
    });

    it('v1 データ（segment なし）は区切りなしのフラット表示', () => {
        const v1Turns: DiscussionTurn[] = [
            { speaker: 'A', text: '一言目' },
            { speaker: 'B', text: '二言目' },
        ];
        render(<ScriptView turns={v1Turns} />);
        expect(screen.queryAllByRole('separator')).toHaveLength(0);
        expect(screen.getByText('一言目')).toBeInTheDocument();
        expect(screen.getByText('二言目')).toBeInTheDocument();
    });

    it('segments マップに見出しがない id はそのまま表示する', () => {
        render(<ScriptView turns={[{ speaker: 'A', text: 'x', segment: 'closing' }]} />);
        expect(screen.getByText('closing')).toBeInTheDocument();
    });
});

describe('ChecksBadge', () => {
    it('passed=true で「合格」バッジ', () => {
        render(<ChecksBadge checks={{ passed: true, results: [] }} />);
        expect(screen.getByText('合格')).toBeInTheDocument();
    });

    it('passed=false で「要再生成」バッジ', () => {
        render(<ChecksBadge checks={{ passed: false, results: [] }} />);
        expect(screen.getByText('要再生成')).toBeInTheDocument();
    });
});
