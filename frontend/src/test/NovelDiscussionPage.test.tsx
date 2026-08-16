/**
 * NovelDiscussionPage: B-28 番組台本 UI（stage 表示・checks バッジ・再生成・履歴削除）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, fireEvent, screen } from '@testing-library/react';

vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock('../hooks/novel_db', () => ({
    useNovelDbBooks: vi.fn(),
}));
vi.mock('../hooks/novel_db/useDiscussion', () => ({
    useDiscussion: vi.fn(),
}));

import type { DiscussionHistoryItem } from '@/features/novel_db/api';
import { useNovelDbBooks } from '@/hooks/novel_db';
import { useDiscussion, type UseDiscussionReturn } from '@/hooks/novel_db/useDiscussion';
import NovelDiscussionPage from '@/pages/NovelDiscussionPage';

const BOOKS = [
    {
        name: '銀河鉄道の夜',
        authors: [],
        series_id: null,
        series_title: null,
        is_indexed: true,
        page_count: 100,
        indexed_at: null,
        thumbnail_url: null,
        ocr_done_at: null,
        volume: null,
        publisher: null,
        asin: null,
        series_index: null,
        read_state: 'unread' as const,
    },
];

function makeReturn(overrides: Partial<UseDiscussionReturn> = {}): UseDiscussionReturn {
    return {
        selectedBook: '銀河鉄道の夜',
        setSelectedBook: vi.fn(),
        turns: [],
        segments: {},
        stage: null,
        checks: null,
        isGenerating: false,
        error: null,
        canGenerate: true,
        history: [],
        historyLoading: false,
        handleGenerate: vi.fn(),
        handleRegenerate: vi.fn(),
        handleCancel: vi.fn(),
        handleDelete: vi.fn(),
        bottomRef: { current: null },
        ...overrides,
    };
}

describe('NovelDiscussionPage', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.mocked(useNovelDbBooks).mockReturnValue({
            books: BOOKS,
            series: [],
            isLoading: false,
            error: null,
            refetch: vi.fn(),
        });
        vi.mocked(useDiscussion).mockReturnValue(makeReturn());
    });

    it('タイトルとホスト名が表示され、ペルソナ UI・往復数スライダーは存在しない', () => {
        render(<NovelDiscussionPage />);
        expect(screen.getByText('読書会 番組台本')).toBeInTheDocument();
        expect(screen.getByText(/レイ ＆ ミオ/)).toBeInTheDocument();
        expect(screen.queryByText(/キャラクター A/)).toBeNull();
        expect(screen.queryByText(/往復数/)).toBeNull();
        expect(screen.queryByRole('slider')).toBeNull();
    });

    it('生成ボタンで handleGenerate が呼ばれる', () => {
        const ret = makeReturn();
        vi.mocked(useDiscussion).mockReturnValue(ret);
        render(<NovelDiscussionPage />);
        fireEvent.click(screen.getByText('台本を生成'));
        expect(ret.handleGenerate).toHaveBeenCalledTimes(1);
    });

    it('stage=planning で「構成を考え中…」、scripting で「台本を執筆中…」を表示', () => {
        vi.mocked(useDiscussion).mockReturnValue(
            makeReturn({ isGenerating: true, stage: 'planning' }),
        );
        const { rerender } = render(<NovelDiscussionPage />);
        expect(screen.getByText('構成を考え中…（数分かかります）')).toBeInTheDocument();

        vi.mocked(useDiscussion).mockReturnValue(
            makeReturn({ isGenerating: true, stage: 'scripting' }),
        );
        rerender(<NovelDiscussionPage />);
        expect(screen.getByText('台本を執筆中…')).toBeInTheDocument();
        // 生成中は中止ボタンが出る
        expect(screen.getByText('中止')).toBeInTheDocument();
    });

    it('生成結果はセグメント見出し付きで表示される', () => {
        vi.mocked(useDiscussion).mockReturnValue(
            makeReturn({
                turns: [
                    { speaker: 'A', text: 'つかみ', segment: 'op_hook' },
                    { speaker: 'B', text: '返し', segment: 'op_hook' },
                ],
                segments: { op_hook: 'OPフック' },
            }),
        );
        render(<NovelDiscussionPage />);
        expect(screen.getByText('OPフック')).toBeInTheDocument();
        expect(screen.getByText('つかみ')).toBeInTheDocument();
    });

    it('checks 不合格時: 要再生成バッジ + 不合格項目 + 再生成ボタン', () => {
        const ret = makeReturn({
            turns: [{ speaker: 'A', text: 'x', segment: 'op_hook' }],
            segments: { op_hook: 'OPフック' },
            checks: {
                passed: false,
                results: [
                    { id: 'M1', label: '字数 3,000〜4,500', passed: false, detail: '2,681字' },
                    { id: 'M2', label: 'セグメント数', passed: true, detail: '5' },
                ],
            },
        });
        vi.mocked(useDiscussion).mockReturnValue(ret);
        render(<NovelDiscussionPage />);

        expect(screen.getByText('要再生成')).toBeInTheDocument();
        expect(screen.getByText(/字数 3,000〜4,500 — 2,681字/)).toBeInTheDocument();
        // 合格した項目は列挙しない
        expect(screen.queryByText(/セグメント数/)).toBeNull();

        fireEvent.click(screen.getByText('再生成'));
        expect(ret.handleRegenerate).toHaveBeenCalledTimes(1);
    });

    it('checks 合格時: 合格バッジ + エクスポートボタン', () => {
        vi.mocked(useDiscussion).mockReturnValue(
            makeReturn({
                turns: [{ speaker: 'A', text: 'x', segment: 'op_hook' }],
                segments: { op_hook: 'OPフック' },
                checks: { passed: true, results: [] },
            }),
        );
        render(<NovelDiscussionPage />);
        expect(screen.getByText('合格')).toBeInTheDocument();
        expect(screen.getByText('コピー')).toBeInTheDocument();
        expect(screen.getByText('MD ダウンロード')).toBeInTheDocument();
    });

    it('履歴カードの削除フローで handleDelete が呼ばれる', () => {
        const item: DiscussionHistoryItem = {
            filename: 'h.json',
            created_at: null,
            personas: [
                { name: 'レイ', style_description: '' },
                { name: 'ミオ', style_description: '' },
            ],
            turn_count: 1,
            turns: [{ speaker: 'A', text: 'x', segment: 'op_hook' }],
            format_version: 2,
            segments: [{ id: 'op_hook', title: 'OPフック' }],
            checks: { passed: true, results: [] },
        };
        const ret = makeReturn({ history: [item] });
        vi.mocked(useDiscussion).mockReturnValue(ret);
        render(<NovelDiscussionPage />);

        fireEvent.click(screen.getByLabelText('台本を削除'));
        fireEvent.click(screen.getByText('削除'));
        expect(ret.handleDelete).toHaveBeenCalledWith('h.json');
    });
});
