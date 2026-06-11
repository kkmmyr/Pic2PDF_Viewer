/**
 * useBookMeta.reorderSeries / assignSeries のユニットテスト（Phase 18-1）。
 *
 * 実行方法:
 *   cd frontend && npx vitest run src/test/useBookMeta.reorderSeries.test.ts
 */
import React from 'react';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi, describe, it, expect, beforeEach } from 'vitest';

vi.mock('../config/api_client', () => ({
    default: {
        get: vi.fn(),
        post: vi.fn(),
    },
}));

import apiClient from '@/config/api_client';
import { useBookMeta } from '@/hooks/library/useBookMeta';

const createWrapper = () => {
    const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    });
    return ({ children }: { children: React.ReactNode }) =>
        React.createElement(QueryClientProvider, { client: queryClient }, children);
};

const mockedGet = apiClient.get as ReturnType<typeof vi.fn>;
const mockedPost = apiClient.post as ReturnType<typeof vi.fn>;

const INITIAL_META = {
    'vol1.pdf': { authors: [], series_id: 's1', series_title: 'テスト', series_index: 1 },
    'vol2.pdf': { authors: [], series_id: 's1', series_title: 'テスト', series_index: 2 },
    'vol3.pdf': { authors: [], series_id: 's1', series_title: 'テスト', series_index: 3 },
};

describe('useBookMeta.reorderSeries', () => {
    beforeEach(() => {
        mockedGet.mockReset();
        mockedPost.mockReset();
    });

    it('成功時: names の順序で series_index が 1-indexed で振り直される', async () => {
        mockedGet.mockResolvedValue(structuredClone(INITIAL_META));
        mockedPost.mockResolvedValue({});

        const { result } = renderHook(() => useBookMeta('doujin'), { wrapper: createWrapper() });
        await waitFor(() => expect(result.current.meta['vol1.pdf']?.series_index).toBe(1));

        // vol3 → vol1 → vol2 の順に並べ替える
        await act(async () => {
            await result.current.reorderSeries('', ['vol3.pdf', 'vol1.pdf', 'vol2.pdf'], 's1');
        });

        expect(result.current.meta['vol3.pdf']?.series_index).toBe(1);
        expect(result.current.meta['vol1.pdf']?.series_index).toBe(2);
        expect(result.current.meta['vol2.pdf']?.series_index).toBe(3);
    });

    it('楽観的更新: API 応答前に series_index が即時更新される', async () => {
        mockedGet.mockResolvedValue(structuredClone(INITIAL_META));

        // POST は明示的に解決するまで保留にする
        let resolvePost!: (value: unknown) => void;
        mockedPost.mockReturnValue(
            new Promise((r) => {
                resolvePost = r;
            }),
        );

        const { result } = renderHook(() => useBookMeta('doujin'), { wrapper: createWrapper() });
        await waitFor(() => expect(result.current.meta['vol1.pdf']?.series_index).toBe(1));

        // 非同期操作を起動（await しない）
        let pending!: Promise<void>;
        act(() => {
            pending = result.current.reorderSeries('', ['vol2.pdf', 'vol1.pdf', 'vol3.pdf'], 's1');
        });

        // API 未解決の状態で楽観的更新が反映されていることを確認
        await waitFor(() => expect(result.current.meta['vol2.pdf']?.series_index).toBe(1));
        expect(result.current.meta['vol1.pdf']?.series_index).toBe(2);
        expect(result.current.meta['vol3.pdf']?.series_index).toBe(3);

        // POST を解決してクリーンアップ
        await act(async () => {
            resolvePost({});
            await pending;
        });
    });

    it('API エラー時: series_index が元の値にロールバックされ error が再スローされる', async () => {
        mockedGet.mockResolvedValue(structuredClone(INITIAL_META));
        mockedPost.mockRejectedValue(new Error('network error'));

        const { result } = renderHook(() => useBookMeta('doujin'), { wrapper: createWrapper() });
        await waitFor(() => expect(result.current.meta['vol1.pdf']?.series_index).toBe(1));

        let thrown: unknown;
        await act(async () => {
            try {
                await result.current.reorderSeries('', ['vol3.pdf', 'vol1.pdf', 'vol2.pdf'], 's1');
            } catch (e) {
                thrown = e;
            }
        });

        // エラーが再スローされている
        expect(thrown).toBeInstanceOf(Error);

        // series_index が元の値に戻っている（ロールバック成功）
        expect(result.current.meta['vol1.pdf']?.series_index).toBe(1);
        expect(result.current.meta['vol2.pdf']?.series_index).toBe(2);
        expect(result.current.meta['vol3.pdf']?.series_index).toBe(3);
    });

    it('ロールバック後も authors / series_title などの他フィールドが保持される', async () => {
        const metaWithAuthors = {
            'vol1.pdf': {
                authors: ['作者A'],
                series_id: 's1',
                series_title: 'テスト',
                series_index: 1,
            },
            'vol2.pdf': {
                authors: ['作者B'],
                series_id: 's1',
                series_title: 'テスト',
                series_index: 2,
            },
        };
        mockedGet.mockResolvedValue(metaWithAuthors);
        mockedPost.mockRejectedValue(new Error('error'));

        const { result } = renderHook(() => useBookMeta('doujin'), { wrapper: createWrapper() });
        await waitFor(() => expect(result.current.meta['vol1.pdf']?.series_index).toBe(1));

        await act(async () => {
            try {
                await result.current.reorderSeries('', ['vol2.pdf', 'vol1.pdf'], 's1');
            } catch {
                // expected
            }
        });

        // ロールバック後も他フィールドが保持されている
        expect(result.current.meta['vol1.pdf']?.series_index).toBe(1);
        expect(result.current.meta['vol1.pdf']?.authors).toEqual(['作者A']);
        expect(result.current.meta['vol1.pdf']?.series_title).toBe('テスト');
        expect(result.current.meta['vol2.pdf']?.series_index).toBe(2);
        expect(result.current.meta['vol2.pdf']?.authors).toEqual(['作者B']);
    });
});

describe('useBookMeta.assignSeries', () => {
    beforeEach(() => {
        mockedGet.mockReset();
        mockedPost.mockReset();
    });

    it('index 配列で複数冊に個別の巻数を割り当てられる', async () => {
        mockedGet.mockResolvedValue({});
        mockedPost.mockResolvedValue({ id: 'series-abc', updated_count: 3 });

        const { result } = renderHook(() => useBookMeta('doujin'), { wrapper: createWrapper() });
        await waitFor(() => expect(mockedGet).toHaveBeenCalled());

        await act(async () => {
            await result.current.assignSeries('', ['vol1.pdf', 'vol3.pdf', 'vol5.pdf'], {
                title: 'テスト',
                index: [1, 3, 5],
            });
        });

        expect(result.current.meta['vol1.pdf']?.series_index).toBe(1);
        expect(result.current.meta['vol3.pdf']?.series_index).toBe(3);
        expect(result.current.meta['vol5.pdf']?.series_index).toBe(5);
    });

    it('index スカラーで全冊に同じ巻数が割り当てられる', async () => {
        mockedGet.mockResolvedValue({});
        mockedPost.mockResolvedValue({ id: 'series-xyz', updated_count: 2 });

        const { result } = renderHook(() => useBookMeta('doujin'), { wrapper: createWrapper() });
        await waitFor(() => expect(mockedGet).toHaveBeenCalled());

        await act(async () => {
            await result.current.assignSeries('', ['book1.pdf', 'book2.pdf'], {
                title: 'スカラーテスト',
                index: 7,
            });
        });

        expect(result.current.meta['book1.pdf']?.series_index).toBe(7);
        expect(result.current.meta['book2.pdf']?.series_index).toBe(7);
    });

    it('index 配列の長さが names と不一致なら throw し API を呼ばない', async () => {
        mockedGet.mockResolvedValue({});
        const { result } = renderHook(() => useBookMeta('doujin'), { wrapper: createWrapper() });
        await waitFor(() => expect(mockedGet).toHaveBeenCalled());

        let thrown: unknown;
        await act(async () => {
            try {
                await result.current.assignSeries('', ['a.pdf', 'b.pdf'], {
                    title: 'エラーテスト',
                    index: [1], // 長さ不一致
                });
            } catch (e) {
                thrown = e;
            }
        });

        expect(thrown).toBeInstanceOf(Error);
        expect(mockedPost).not.toHaveBeenCalled();
    });

    it('assignSeries 後は既存フィールド (authors / view_count) が保持される', async () => {
        mockedGet.mockResolvedValue({
            'book.pdf': { authors: ['作者X'], view_count: 5 },
        });
        mockedPost.mockResolvedValue({ id: 'confirmed-id', updated_count: 1 });

        const { result } = renderHook(() => useBookMeta('doujin'), { wrapper: createWrapper() });
        await waitFor(() => expect(result.current.meta['book.pdf']?.authors).toEqual(['作者X']));

        await act(async () => {
            await result.current.assignSeries('', ['book.pdf'], {
                title: '新シリーズ',
                index: 2,
            });
        });

        const entry = result.current.meta['book.pdf'];
        expect(entry?.series_id).toBe('confirmed-id');
        expect(entry?.series_title).toBe('新シリーズ');
        expect(entry?.series_index).toBe(2);
        // 既存フィールドが保持されている
        expect(entry?.authors).toEqual(['作者X']);
        expect(entry?.view_count).toBe(5);
    });
});
