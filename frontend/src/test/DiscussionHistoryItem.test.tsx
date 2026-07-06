/**
 * DiscussionHistoryItemCard: v2 セグメント表示・checks バッジ・削除フロー・v1 互換（B-28）。
 */
import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent, screen } from '@testing-library/react';

vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import DiscussionHistoryItemCard from '@/components/novel_db/DiscussionHistoryItem';
import type { DiscussionHistoryItem } from '@/features/novel_db/api';

const V2_ITEM: DiscussionHistoryItem = {
    filename: '20260707_script.json',
    created_at: '2026-07-07 01:00:00',
    personas: [
        { name: 'レイ', style_description: '' },
        { name: 'ミオ', style_description: '' },
    ],
    turn_count: 3,
    turns: [
        { speaker: 'A', text: 'つかみ', segment: 'op_hook' },
        { speaker: 'B', text: '返し', segment: 'op_hook' },
        { speaker: 'A', text: '本題', segment: 'theme1' },
    ],
    format_version: 2,
    segments: [
        { id: 'op_hook', title: 'OPフック' },
        { id: 'theme1', title: 'テーマ1' },
    ],
    checks: {
        passed: true,
        results: [{ id: 'M1', label: '字数 3,000〜4,500', passed: true, detail: '3,500字' }],
    },
};

const V1_ITEM: DiscussionHistoryItem = {
    filename: 'old.json',
    created_at: '2026-05-01 01:00:00',
    personas: [
        { name: '批評家', style_description: '批評家・敬語丁寧' },
        { name: 'ファン', style_description: 'ファン・フランク' },
    ],
    turn_count: 2,
    turns: [
        { speaker: 'A', text: '一言目' },
        { speaker: 'B', text: '二言目' },
    ],
    format_version: 1,
};

describe('DiscussionHistoryItemCard (v2)', () => {
    it('ヘッダに checks バッジが表示され、展開でセグメント見出しが出る', () => {
        render(<DiscussionHistoryItemCard item={V2_ITEM} bookName="テスト本" />);
        expect(screen.getByText('合格')).toBeInTheDocument();
        expect(screen.queryByText('OPフック')).toBeNull();

        fireEvent.click(screen.getByText(/レイ × ミオ/));
        expect(screen.getByText('OPフック')).toBeInTheDocument();
        expect(screen.getByText('テーマ1')).toBeInTheDocument();
        expect(screen.getAllByRole('separator')).toHaveLength(2);
    });

    it('bookName ありで展開するとエクスポートボタンが表示される', () => {
        render(<DiscussionHistoryItemCard item={V2_ITEM} bookName="テスト本" />);
        fireEvent.click(screen.getByText(/レイ × ミオ/));
        expect(screen.getByText('コピー')).toBeInTheDocument();
        expect(screen.getByText('MD ダウンロード')).toBeInTheDocument();
    });

    it('bookName なしではエクスポートボタンを表示しない', () => {
        render(<DiscussionHistoryItemCard item={V2_ITEM} />);
        fireEvent.click(screen.getByText(/レイ × ミオ/));
        expect(screen.queryByText('コピー')).toBeNull();
    });

    it('onDelete 指定時: ゴミ箱 → ConfirmDialog → 削除で onDelete(filename) が呼ばれる', () => {
        const onDelete = vi.fn();
        render(
            <DiscussionHistoryItemCard item={V2_ITEM} bookName="テスト本" onDelete={onDelete} />,
        );

        fireEvent.click(screen.getByLabelText('台本を削除'));
        expect(screen.getByText('台本の削除')).toBeInTheDocument();

        fireEvent.click(screen.getByText('削除'));
        expect(onDelete).toHaveBeenCalledWith('20260707_script.json');
    });

    it('onDelete 未指定時はゴミ箱ボタンを表示しない', () => {
        render(<DiscussionHistoryItemCard item={V2_ITEM} bookName="テスト本" />);
        expect(screen.queryByLabelText('台本を削除')).toBeNull();
    });

    it('ConfirmDialog をキャンセルすると onDelete は呼ばれない', () => {
        const onDelete = vi.fn();
        render(
            <DiscussionHistoryItemCard item={V2_ITEM} bookName="テスト本" onDelete={onDelete} />,
        );

        fireEvent.click(screen.getByLabelText('台本を削除'));
        fireEvent.click(screen.getByText('キャンセル'));
        expect(onDelete).not.toHaveBeenCalled();
    });
});

describe('DiscussionHistoryItemCard (v1 互換)', () => {
    it('従来のフラット表示（区切りなし・ペルソナ名）で表示される', () => {
        render(<DiscussionHistoryItemCard item={V1_ITEM} bookName="旧作" />);
        expect(screen.getByText(/批評家 × ファン/)).toBeInTheDocument();
        expect(screen.queryByText('合格')).toBeNull();
        expect(screen.queryByText('要再生成')).toBeNull();

        fireEvent.click(screen.getByText(/批評家 × ファン/));
        expect(screen.getByText('一言目')).toBeInTheDocument();
        expect(screen.queryAllByRole('separator')).toHaveLength(0);
    });
});
