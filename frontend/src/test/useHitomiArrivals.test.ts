import { renderHook, act, waitFor } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';

vi.mock('../config/api_client', () => ({
    default: { get: vi.fn(), post: vi.fn() },
}));

import apiClient from '@/config/api_client';
import { useHitomiArrivals } from '@/hooks/useHitomiArrivals';
import type { ArrivalItem, NewArrivalsResponse, RunNowResponse } from '@/types/hitomi';

const mockedGet = apiClient.get as ReturnType<typeof vi.fn>;
const mockedPost = apiClient.post as ReturnType<typeof vi.fn>;

function createWrapper() {
    const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false } },
    });
    return ({ children }: { children: React.ReactNode }) =>
        React.createElement(QueryClientProvider, { client: queryClient }, children);
}

const makeItem = (id: number): ArrivalItem => ({
    id,
    artist: `artist-${id}`,
    display_artist: `表示${id}`,
    title: `タイトル${id}`,
    language: 'japanese',
    type: 'doujinshi',
    page_count: 30,
    published_at: '2026-05-01',
    discovered_at: '2026-05-06',
    url: `https://hitomi.la/${id}`,
    dismissed: false,
});

const buildResponse = (items: ArrivalItem[]): NewArrivalsResponse => ({
    items,
    last_run_at: '2026-05-06T10:00:00Z',
    last_run_status: 'ok',
    last_error: null,
});

describe('useHitomiArrivals', () => {
    beforeEach(() => {
        mockedGet.mockReset();
        mockedPost.mockReset();
    });

    it('マウント時に GET /api/hitomi/new-arrivals を呼ぶ', async () => {
        mockedGet.mockResolvedValue(buildResponse([makeItem(1), makeItem(2)]));
        const { result } = renderHook(() => useHitomiArrivals(), { wrapper: createWrapper() });

        await waitFor(() => expect(mockedGet).toHaveBeenCalled());
        expect(mockedGet).toHaveBeenCalledWith('/api/hitomi/new-arrivals');
        await waitFor(() => expect(result.current.items).toHaveLength(2));
        expect(result.current.lastRunAt).toBe('2026-05-06T10:00:00Z');
        expect(result.current.lastRunStatus).toBe('ok');
        expect(result.current.lastError).toBeNull();
        expect(result.current.loading).toBe(false);
    });

    it('GET 失敗時に error が設定される（loading は false に戻る）', async () => {
        mockedGet.mockRejectedValue(new Error('network down'));
        const { result } = renderHook(() => useHitomiArrivals(), { wrapper: createWrapper() });

        await waitFor(() => expect(result.current.loading).toBe(false));
        expect(result.current.error).toBe('network down');
    });

    it('dismiss(id) で楽観的に該当 item を取り除き POST する', async () => {
        mockedGet.mockResolvedValue(buildResponse([makeItem(1), makeItem(2), makeItem(3)]));
        mockedPost.mockResolvedValue(undefined);

        const { result } = renderHook(() => useHitomiArrivals(), { wrapper: createWrapper() });
        await waitFor(() => expect(result.current.items).toHaveLength(3));

        await act(async () => {
            await result.current.dismiss(2);
        });

        expect(mockedPost).toHaveBeenCalledWith('/api/hitomi/dismiss/2');
        expect(result.current.items.map((it) => it.id)).toEqual([1, 3]);
    });

    it('dismiss POST 失敗時にロールバックして throw する', async () => {
        mockedGet.mockResolvedValue(buildResponse([makeItem(1), makeItem(2)]));
        mockedPost.mockRejectedValue(new Error('server error'));

        const { result } = renderHook(() => useHitomiArrivals(), { wrapper: createWrapper() });
        await waitFor(() => expect(result.current.items).toHaveLength(2));

        let thrown: unknown;
        await act(async () => {
            try {
                await result.current.dismiss(1);
            } catch (e) {
                thrown = e;
            }
        });

        expect(thrown).toBeInstanceOf(Error);
        // ロールバック後、items は元に戻る
        expect(result.current.items.map((it) => it.id)).toEqual([1, 2]);
    });

    it('dismissAll で楽観的に items を空にし POST する', async () => {
        mockedGet.mockResolvedValue(buildResponse([makeItem(1), makeItem(2)]));
        mockedPost.mockResolvedValue(undefined);

        const { result } = renderHook(() => useHitomiArrivals(), { wrapper: createWrapper() });
        await waitFor(() => expect(result.current.items).toHaveLength(2));

        await act(async () => {
            await result.current.dismissAll();
        });

        expect(mockedPost).toHaveBeenCalledWith('/api/hitomi/dismiss-all');
        expect(result.current.items).toHaveLength(0);
    });

    it('dismissAll 失敗時にロールバック', async () => {
        mockedGet.mockResolvedValue(buildResponse([makeItem(1)]));
        mockedPost.mockRejectedValue(new Error('boom'));

        const { result } = renderHook(() => useHitomiArrivals(), { wrapper: createWrapper() });
        await waitFor(() => expect(result.current.items).toHaveLength(1));

        await act(async () => {
            try {
                await result.current.dismissAll();
            } catch {
                // expected
            }
        });

        expect(result.current.items).toHaveLength(1);
    });

    it('runNow は POST /api/hitomi/run-now を呼んで last_run_stats を返し、refresh も走る', async () => {
        mockedGet.mockResolvedValueOnce(buildResponse([makeItem(1)]));

        const runResp: RunNowResponse = {
            exit_code: 0,
            last_run_at: '2026-05-06T11:00:00Z',
            last_run_status: 'ok',
            last_error: null,
            last_run_stats: { added: 3, skipped: 1, errors: 0 },
        };
        mockedPost.mockResolvedValue(runResp);

        // refresh で再度 GET が呼ばれる → 新着 2 件追加された状態
        mockedGet.mockResolvedValueOnce(buildResponse([makeItem(1), makeItem(2), makeItem(3)]));

        const { result } = renderHook(() => useHitomiArrivals(), { wrapper: createWrapper() });
        await waitFor(() => expect(result.current.items).toHaveLength(1));

        let stats;
        await act(async () => {
            stats = await result.current.runNow();
        });

        expect(stats).toEqual({ added: 3, skipped: 1, errors: 0 });
        expect(mockedPost).toHaveBeenCalledWith(
            '/api/hitomi/run-now',
            undefined,
            expect.objectContaining({ timeout: 120_000 }),
        );
        await waitFor(() => expect(result.current.items).toHaveLength(3));
    });

    it('runNow の最中は running=true、完了で false に戻る', async () => {
        mockedGet.mockResolvedValue(buildResponse([]));
        let resolvePost!: (v: RunNowResponse) => void;
        mockedPost.mockReturnValue(
            new Promise((r) => {
                resolvePost = r;
            }),
        );

        const { result } = renderHook(() => useHitomiArrivals(), { wrapper: createWrapper() });
        await waitFor(() => expect(result.current.loading).toBe(false));

        let pending!: Promise<unknown>;
        act(() => {
            pending = result.current.runNow();
        });
        await waitFor(() => expect(result.current.running).toBe(true));

        await act(async () => {
            resolvePost({
                exit_code: 0,
                last_run_at: null,
                last_run_status: 'ok',
                last_error: null,
                last_run_stats: null,
            });
            await pending;
        });

        expect(result.current.running).toBe(false);
    });

    it('refresh を直接呼べる', async () => {
        mockedGet.mockResolvedValue(buildResponse([makeItem(1)]));
        const { result } = renderHook(() => useHitomiArrivals(), { wrapper: createWrapper() });
        await waitFor(() => expect(mockedGet).toHaveBeenCalledTimes(1));

        mockedGet.mockResolvedValue(buildResponse([makeItem(2)]));
        await act(async () => {
            await result.current.refresh();
        });

        expect(mockedGet).toHaveBeenCalledTimes(2);
        expect(result.current.items[0].id).toBe(2);
    });
});
