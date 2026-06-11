import React from 'react';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi, describe, it, expect, beforeEach } from 'vitest';

vi.mock('../config/api_client', () => ({
    default: { get: vi.fn(), post: vi.fn() },
}));

import apiClient from '@/config/api_client';
import { useBookMetaCore } from '@/hooks/library/useBookMetaCore';
import { useBookSeries } from '@/hooks/library/useBookSeries';
import type { BookMetaMap } from '@/types';

const mockedGet = apiClient.get as ReturnType<typeof vi.fn>;
const mockedPost = apiClient.post as ReturnType<typeof vi.fn>;

const createWrapper = () => {
    const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    });
    return ({ children }: { children: React.ReactNode }) =>
        React.createElement(QueryClientProvider, { client: queryClient }, children);
};

function useCombined(source: string) {
    const core = useBookMetaCore(source);
    const series = useBookSeries(source);
    return { ...core, ...series };
}

const renderCombined = (initialMeta: BookMetaMap = {}) => {
    mockedGet.mockResolvedValue(initialMeta);
    return renderHook(() => useCombined('doujin'), { wrapper: createWrapper() });
};

describe('useBookSeries', () => {
    beforeEach(() => {
        mockedGet.mockReset();
        mockedPost.mockReset();
    });

    describe('assignSeries', () => {
        it('スカラー index で全冊に同じ index が割り当てられる', async () => {
            mockedPost.mockResolvedValue({ id: 'sid-X', updated_count: 2 });
            const { result } = renderCombined();
            await waitFor(() => expect(mockedGet).toHaveBeenCalled());

            await act(async () => {
                await result.current.assignSeries('', ['a.pdf', 'b.pdf'], {
                    title: 'シリーズZ',
                    index: 7,
                });
            });

            expect(result.current.meta['a.pdf']?.series_id).toBe('sid-X');
            expect(result.current.meta['a.pdf']?.series_index).toBe(7);
            expect(result.current.meta['b.pdf']?.series_index).toBe(7);
        });

        it('配列 index で個別に割り当てられる', async () => {
            mockedPost.mockResolvedValue({ id: 'sid-Y', updated_count: 3 });
            const { result } = renderCombined();
            await waitFor(() => expect(mockedGet).toHaveBeenCalled());

            await act(async () => {
                await result.current.assignSeries('', ['a.pdf', 'b.pdf', 'c.pdf'], {
                    title: 'シリーズY',
                    index: [1, 3, 5],
                });
            });

            expect(result.current.meta['a.pdf']?.series_index).toBe(1);
            expect(result.current.meta['b.pdf']?.series_index).toBe(3);
            expect(result.current.meta['c.pdf']?.series_index).toBe(5);
        });

        it('index 配列の長さが names と異なると throw（API は呼ばない）', async () => {
            const { result } = renderCombined();
            await waitFor(() => expect(mockedGet).toHaveBeenCalled());

            let thrown: unknown;
            await act(async () => {
                try {
                    await result.current.assignSeries('', ['a.pdf', 'b.pdf'], {
                        title: 'X',
                        index: [1],
                    });
                } catch (e) {
                    thrown = e;
                }
            });
            expect(thrown).toBeInstanceOf(Error);
            expect(mockedPost).not.toHaveBeenCalled();
        });

        it('既存エントリの authors / view_count は保持される', async () => {
            mockedPost.mockResolvedValue({ id: 'sid', updated_count: 1 });
            const { result } = renderCombined({
                'a.pdf': { authors: ['作者X'], view_count: 5 },
            });
            await waitFor(() => expect(result.current.meta['a.pdf']).toBeDefined());

            await act(async () => {
                await result.current.assignSeries('', ['a.pdf'], { title: 'X', index: 1 });
            });

            expect(result.current.meta['a.pdf']?.authors).toEqual(['作者X']);
            expect(result.current.meta['a.pdf']?.view_count).toBe(5);
        });

        it('戻り値はバックエンドが返した series_id', async () => {
            mockedPost.mockResolvedValue({ id: 'auto-generated-sid', updated_count: 1 });
            const { result } = renderCombined();
            await waitFor(() => expect(mockedGet).toHaveBeenCalled());

            let returnedId: string | undefined;
            await act(async () => {
                returnedId = await result.current.assignSeries('', ['a.pdf'], {
                    title: 'X',
                    index: 1,
                });
            });
            expect(returnedId).toBe('auto-generated-sid');
        });

        it('id を明示すると body に含まれて送信される', async () => {
            mockedPost.mockResolvedValue({ id: 'fixed-sid', updated_count: 1 });
            const { result } = renderCombined();
            await waitFor(() => expect(mockedGet).toHaveBeenCalled());

            await act(async () => {
                await result.current.assignSeries('', ['a.pdf'], {
                    title: 'X',
                    index: 1,
                    id: 'fixed-sid',
                });
            });
            expect(mockedPost.mock.calls[0][1]).toMatchObject({ id: 'fixed-sid' });
        });
    });

    describe('unassignSeries', () => {
        it('series_id / series_title / series_index が削除される', async () => {
            mockedPost.mockResolvedValue(undefined);
            const { result } = renderCombined({
                'a.pdf': {
                    authors: ['X'],
                    series_id: 's1',
                    series_title: 'シリーズA',
                    series_index: 2,
                },
            });
            await waitFor(() => expect(result.current.meta['a.pdf']?.series_id).toBe('s1'));

            await act(async () => {
                await result.current.unassignSeries('', ['a.pdf']);
            });

            expect(result.current.meta['a.pdf']?.series_id).toBeUndefined();
            expect(result.current.meta['a.pdf']?.series_title).toBeUndefined();
            expect(result.current.meta['a.pdf']?.series_index).toBeUndefined();
            // authors は残る
            expect(result.current.meta['a.pdf']?.authors).toEqual(['X']);
        });

        it('対象エントリ不在でも例外なし', async () => {
            mockedPost.mockResolvedValue(undefined);
            const { result } = renderCombined();
            await waitFor(() => expect(mockedGet).toHaveBeenCalled());

            await act(async () => {
                await result.current.unassignSeries('', ['missing.pdf']);
            });
            // meta に missing.pdf は無いまま
            expect(result.current.meta['missing.pdf']).toBeUndefined();
        });
    });

    describe('reorderSeries', () => {
        it('成功時: names の順序で series_index が 1, 2, 3, ... に振り直される', async () => {
            mockedPost.mockResolvedValue(undefined);
            const { result } = renderCombined({
                'v1.pdf': { series_id: 's1', series_index: 1, authors: [] },
                'v2.pdf': { series_id: 's1', series_index: 2, authors: [] },
                'v3.pdf': { series_id: 's1', series_index: 3, authors: [] },
            });
            await waitFor(() => expect(result.current.meta['v1.pdf']).toBeDefined());

            await act(async () => {
                await result.current.reorderSeries('', ['v3.pdf', 'v1.pdf', 'v2.pdf'], 's1');
            });

            expect(result.current.meta['v3.pdf']?.series_index).toBe(1);
            expect(result.current.meta['v1.pdf']?.series_index).toBe(2);
            expect(result.current.meta['v2.pdf']?.series_index).toBe(3);
        });

        it('失敗時: ロールバックして元の series_index に戻り、再 throw', async () => {
            mockedPost.mockRejectedValue(new Error('ネットワークエラー'));
            const { result } = renderCombined({
                'v1.pdf': { series_id: 's1', series_index: 1, authors: ['X'] },
                'v2.pdf': { series_id: 's1', series_index: 2, authors: ['Y'] },
            });
            await waitFor(() => expect(result.current.meta['v1.pdf']).toBeDefined());

            let thrown: unknown;
            await act(async () => {
                try {
                    await result.current.reorderSeries('', ['v2.pdf', 'v1.pdf'], 's1');
                } catch (e) {
                    thrown = e;
                }
            });

            expect(thrown).toBeInstanceOf(Error);
            // ロールバック後の値
            expect(result.current.meta['v1.pdf']?.series_index).toBe(1);
            expect(result.current.meta['v2.pdf']?.series_index).toBe(2);
            // authors も保持
            expect(result.current.meta['v1.pdf']?.authors).toEqual(['X']);
            expect(result.current.meta['v2.pdf']?.authors).toEqual(['Y']);
        });
    });
});
