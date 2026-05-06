import { renderHook, act, waitFor } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';

vi.mock('../config/api_client', () => ({
    default: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
}));

import apiClient from '../config/api_client';
import { useHitomiWatchlist } from '../hooks/useHitomiWatchlist';
import type { WatchlistEntry, WatchlistResponse } from '../types/hitomi';

const mockedGet = apiClient.get as ReturnType<typeof vi.fn>;
const mockedPost = apiClient.post as ReturnType<typeof vi.fn>;
const mockedDelete = apiClient.delete as ReturnType<typeof vi.fn>;

const makeEntry = (display: string, normalized = display.toLowerCase()): WatchlistEntry => ({
    display_name: display,
    normalized,
    language: 'japanese',
    added_at: '2026-05-06',
});

const buildResp = (artists: WatchlistEntry[]): WatchlistResponse => ({ artists });

describe('useHitomiWatchlist', () => {
    beforeEach(() => {
        mockedGet.mockReset();
        mockedPost.mockReset();
        mockedDelete.mockReset();
    });

    it('マウント時に GET /api/hitomi/watchlist を呼び artists を初期化', async () => {
        mockedGet.mockResolvedValue(buildResp([makeEntry('A'), makeEntry('B')]));
        const { result } = renderHook(() => useHitomiWatchlist());

        await waitFor(() => expect(mockedGet).toHaveBeenCalled());
        expect(mockedGet).toHaveBeenCalledWith('/api/hitomi/watchlist');
        await waitFor(() => expect(result.current.artists).toHaveLength(2));
        expect(result.current.loading).toBe(false);
        expect(result.current.error).toBeNull();
    });

    it('GET 失敗で error が設定され、loading は false に戻る', async () => {
        mockedGet.mockRejectedValue(new Error('network'));
        const { result } = renderHook(() => useHitomiWatchlist());

        await waitFor(() => expect(result.current.loading).toBe(false));
        expect(result.current.error).toBe('network');
    });

    it('addArtist で POST → refresh が走り、戻り値に display_name と normalized を含む', async () => {
        mockedGet.mockResolvedValueOnce(buildResp([]));
        mockedPost.mockResolvedValue({ message: 'ok', normalized: 'foo' });
        mockedGet.mockResolvedValueOnce(buildResp([makeEntry('Foo', 'foo')]));

        const { result } = renderHook(() => useHitomiWatchlist());
        await waitFor(() => expect(result.current.loading).toBe(false));

        let returned: WatchlistEntry | undefined;
        await act(async () => {
            returned = await result.current.addArtist(' Foo ', 'japanese');
        });

        expect(mockedPost).toHaveBeenCalledWith('/api/hitomi/watchlist', {
            display_name: ' Foo ',
            language: 'japanese',
        });
        expect(returned?.display_name).toBe('Foo'); // trim される
        expect(returned?.normalized).toBe('foo');
        expect(returned?.language).toBe('japanese');
        await waitFor(() => expect(result.current.artists).toHaveLength(1));
    });

    it('removeArtist は楽観的に該当エントリを除き DELETE する', async () => {
        mockedGet.mockResolvedValue(
            buildResp([makeEntry('A', 'a'), makeEntry('B', 'b'), makeEntry('C', 'c')]),
        );
        mockedDelete.mockResolvedValue(undefined);

        const { result } = renderHook(() => useHitomiWatchlist());
        await waitFor(() => expect(result.current.artists).toHaveLength(3));

        await act(async () => {
            await result.current.removeArtist('b', 'japanese');
        });

        expect(mockedDelete).toHaveBeenCalled();
        expect(result.current.artists.map((e) => e.normalized)).toEqual(['a', 'c']);
    });

    it('removeArtist は normalized + language の組み合わせで一致したものだけ除く', async () => {
        mockedGet.mockResolvedValue(
            buildResp([
                { ...makeEntry('A', 'a'), language: 'japanese' },
                { ...makeEntry('A', 'a'), language: 'english' },
            ]),
        );
        mockedDelete.mockResolvedValue(undefined);

        const { result } = renderHook(() => useHitomiWatchlist());
        await waitFor(() => expect(result.current.artists).toHaveLength(2));

        await act(async () => {
            await result.current.removeArtist('a', 'japanese');
        });

        expect(result.current.artists).toHaveLength(1);
        expect(result.current.artists[0].language).toBe('english');
    });

    it('removeArtist 失敗時はロールバックして throw する', async () => {
        mockedGet.mockResolvedValue(buildResp([makeEntry('A', 'a'), makeEntry('B', 'b')]));
        mockedDelete.mockRejectedValue(new Error('boom'));

        const { result } = renderHook(() => useHitomiWatchlist());
        await waitFor(() => expect(result.current.artists).toHaveLength(2));

        let thrown: unknown;
        await act(async () => {
            try {
                await result.current.removeArtist('b', 'japanese');
            } catch (e) {
                thrown = e;
            }
        });

        expect(thrown).toBeInstanceOf(Error);
        expect(result.current.artists).toHaveLength(2);
    });

    it('refresh を直接呼べる', async () => {
        mockedGet.mockResolvedValueOnce(buildResp([makeEntry('A')]));
        const { result } = renderHook(() => useHitomiWatchlist());
        await waitFor(() => expect(result.current.artists).toHaveLength(1));

        mockedGet.mockResolvedValueOnce(buildResp([makeEntry('A'), makeEntry('B')]));
        await act(async () => {
            await result.current.refresh();
        });
        expect(result.current.artists).toHaveLength(2);
    });
});
