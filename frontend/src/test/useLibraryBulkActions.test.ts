import { renderHook, act } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { toast } from 'sonner';

vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock('../config/api_client', () => ({
    default: {
        post: vi.fn(),
        delete: vi.fn(),
    },
}));

import { useLibraryBulkActions } from '@/hooks/library/useLibraryBulkActions';
import apiClient from '../config/api_client';

const makeOptions = (overrides: Record<string, unknown> = {}) => ({
    currentPath: '',
    currentSource: 'doujin' as const,
    selectedItems: new Set<string>(['a.pdf', 'b.pdf']),
    showHidden: false,
    seriesFilter: '',
    onClearSelection: vi.fn(),
    onRefresh: vi.fn(),
    bookMeta: {
        updateAuthors: vi.fn().mockResolvedValue(undefined),
        updateGenre: vi.fn().mockResolvedValue(undefined),
        setHidden: vi.fn().mockResolvedValue(undefined),
        assignSeries: vi.fn().mockResolvedValue('sid'),
        unassignSeries: vi.fn().mockResolvedValue(undefined),
        reorderSeries: vi.fn().mockResolvedValue(undefined),
    },
    addGenre: vi.fn().mockResolvedValue(undefined),
    currentGenres: ['既存ジャンル'] as string[],
    ...overrides,
});

describe('useLibraryBulkActions', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    describe('handleBulkApplyGenre', () => {
        it('新規ジャンルは addGenre → updateGenre → onClearSelection の順に呼ぶ', async () => {
            const opts = makeOptions();
            const { result } = renderHook(() => useLibraryBulkActions(opts));

            await act(async () => {
                await result.current.handleBulkApplyGenre('新規ジャンル');
            });

            expect(opts.addGenre).toHaveBeenCalledWith('新規ジャンル');
            expect(opts.bookMeta.updateGenre).toHaveBeenCalledWith(
                '',
                ['a.pdf', 'b.pdf'],
                '新規ジャンル',
            );
            expect(opts.onClearSelection).toHaveBeenCalledTimes(1);
        });

        it('既存ジャンルは addGenre をスキップして updateGenre のみ呼ぶ', async () => {
            const opts = makeOptions();
            const { result } = renderHook(() => useLibraryBulkActions(opts));

            await act(async () => {
                await result.current.handleBulkApplyGenre('既存ジャンル');
            });

            expect(opts.addGenre).not.toHaveBeenCalled();
            expect(opts.bookMeta.updateGenre).toHaveBeenCalledWith(
                '',
                ['a.pdf', 'b.pdf'],
                '既存ジャンル',
            );
            expect(opts.onClearSelection).toHaveBeenCalledTimes(1);
        });

        it('currentGenres が空のときは常に addGenre を呼ぶ', async () => {
            const opts = makeOptions({ currentGenres: [] });
            const { result } = renderHook(() => useLibraryBulkActions(opts));

            await act(async () => {
                await result.current.handleBulkApplyGenre('なんでも');
            });

            expect(opts.addGenre).toHaveBeenCalledWith('なんでも');
        });

        it('PDF のみが updateGenre の対象になる', async () => {
            const opts = makeOptions({
                selectedItems: new Set<string>(['a.pdf', 'folder']),
                currentGenres: [],
            });
            const { result } = renderHook(() => useLibraryBulkActions(opts));

            await act(async () => {
                await result.current.handleBulkApplyGenre('G');
            });

            const [, names] = (opts.bookMeta.updateGenre as ReturnType<typeof vi.fn>).mock.calls[0];
            expect(names).toContain('a.pdf');
            expect(names).not.toContain('folder');
        });
    });

    describe('handleBulkApplyAuthors', () => {
        it('selectedItems 全体（PDF 以外も含む）で updateAuthors を呼ぶ', async () => {
            const opts = makeOptions({ selectedItems: new Set<string>(['a.pdf', 'folder']) });
            const { result } = renderHook(() => useLibraryBulkActions(opts));

            await act(async () => {
                await result.current.handleBulkApplyAuthors(['Author A']);
            });

            const [, names] = (opts.bookMeta.updateAuthors as ReturnType<typeof vi.fn>).mock
                .calls[0];
            expect(names).toContain('a.pdf');
            expect(names).toContain('folder');
            expect(opts.onClearSelection).toHaveBeenCalledTimes(1);
        });
    });

    describe('handleBulkToggleHidden', () => {
        beforeEach(() => {
            vi.mocked(toast.error).mockClear();
        });

        it('PDF が未選択なら何も呼ばない', async () => {
            const opts = makeOptions({ selectedItems: new Set<string>(['folder']) });
            const { result } = renderHook(() => useLibraryBulkActions(opts));

            await act(async () => {
                await result.current.handleBulkToggleHidden();
            });

            expect(opts.bookMeta.setHidden).not.toHaveBeenCalled();
        });

        it('showHidden=false のとき setHidden(true) で非表示にする', async () => {
            const opts = makeOptions({ showHidden: false });
            const { result } = renderHook(() => useLibraryBulkActions(opts));

            await act(async () => {
                await result.current.handleBulkToggleHidden();
            });

            expect(opts.bookMeta.setHidden).toHaveBeenCalledWith('', ['a.pdf', 'b.pdf'], true);
            expect(opts.onClearSelection).toHaveBeenCalledTimes(1);
        });

        it('showHidden=true のとき setHidden(false) で再表示にする', async () => {
            const opts = makeOptions({ showHidden: true });
            const { result } = renderHook(() => useLibraryBulkActions(opts));

            await act(async () => {
                await result.current.handleBulkToggleHidden();
            });

            expect(opts.bookMeta.setHidden).toHaveBeenCalledWith('', ['a.pdf', 'b.pdf'], false);
        });

        it('setHidden 失敗時は toast.error を呼ぶ', async () => {
            const opts = makeOptions();
            opts.bookMeta.setHidden = vi.fn().mockRejectedValue(new Error('失敗'));
            const { result } = renderHook(() => useLibraryBulkActions(opts));

            await act(async () => {
                await result.current.handleBulkToggleHidden();
            });

            expect(toast.error).toHaveBeenCalledWith('失敗');
        });
    });

    describe('handleBulkDelete', () => {
        it('選択中の書籍を削除して一覧と選択状態を更新する', async () => {
            vi.mocked(apiClient.delete).mockResolvedValue({} as never);
            const opts = makeOptions();
            const { result } = renderHook(() => useLibraryBulkActions(opts));

            await act(async () => {
                await result.current.handleBulkDelete();
            });

            expect(apiClient.delete).toHaveBeenCalledWith('/api/pdfs', {
                data: { names: ['a.pdf', 'b.pdf'], path: '', source: 'doujin' },
            });
            expect(opts.onRefresh).toHaveBeenCalledTimes(1);
            expect(opts.onClearSelection).toHaveBeenCalledTimes(1);
            expect(toast.success).toHaveBeenCalledWith('2 件を削除しました');
        });
    });

    describe('handleToggleHiddenOne', () => {
        beforeEach(() => {
            vi.mocked(toast.error).mockClear();
        });

        it('showHidden=false のとき hidden=true で setHidden を呼ぶ', async () => {
            const opts = makeOptions({ showHidden: false });
            const { result } = renderHook(() => useLibraryBulkActions(opts));

            await act(async () => {
                await result.current.handleToggleHiddenOne('a.pdf');
            });

            expect(opts.bookMeta.setHidden).toHaveBeenCalledWith('', ['a.pdf'], true);
        });

        it('setHidden 失敗時は toast.error を呼ぶ', async () => {
            const opts = makeOptions();
            opts.bookMeta.setHidden = vi.fn().mockRejectedValue(new Error('エラー'));
            const { result } = renderHook(() => useLibraryBulkActions(opts));

            await act(async () => {
                await result.current.handleToggleHiddenOne('a.pdf');
            });

            expect(toast.error).toHaveBeenCalledWith('エラー');
        });
    });
});
