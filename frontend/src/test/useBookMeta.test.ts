/**
 * useBookMeta フックのユニットテスト。
 *
 * 実行方法:
 *   cd frontend && npx vitest run
 */
import { renderHook, act, waitFor } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';

// apiClient をモック化（モジュール初期化前に hoist される）
vi.mock('../config/api_client', () => ({
    default: {
        get: vi.fn(),
        post: vi.fn(),
        patch: vi.fn(),
    },
}));

import apiClient from '../config/api_client';
import { useBookMeta } from '../hooks/useBookMeta';

const mockedGet = apiClient.get as ReturnType<typeof vi.fn>;
const mockedPost = apiClient.post as ReturnType<typeof vi.fn>;
const mockedPatch = apiClient.patch as ReturnType<typeof vi.fn>;

describe('useBookMeta', () => {
    beforeEach(() => {
        mockedGet.mockReset();
        mockedPost.mockReset();
        mockedPatch.mockReset();
    });

    it('マウント時に GET /api/meta を実行して状態を初期化する', async () => {
        mockedGet.mockResolvedValue({
            'book.pdf': { authors: ['サークルA'], view_count: 3, last_viewed_at: 1000 },
        });
        const { result } = renderHook(() => useBookMeta('generated'));

        await waitFor(() => expect(mockedGet).toHaveBeenCalledTimes(1));
        expect(result.current.getAuthors('', 'book.pdf')).toEqual(['サークルA']);
        expect(result.current.getViewCount('', 'book.pdf')).toBe(3);
        expect(result.current.getLastViewedAt('', 'book.pdf')).toBe(1000);
    });

    it('GET 失敗時は空 meta にフォールバック', async () => {
        mockedGet.mockRejectedValue(new Error('boom'));
        const { result } = renderHook(() => useBookMeta('generated'));

        await waitFor(() => expect(mockedGet).toHaveBeenCalled());
        expect(result.current.meta).toEqual({});
        expect(result.current.getViewCount('', 'any.pdf')).toBe(0);
        expect(result.current.getLastViewedAt('', 'any.pdf')).toBeUndefined();
    });

    it('getViewCount: 未記録は 0', async () => {
        mockedGet.mockResolvedValue({});
        const { result } = renderHook(() => useBookMeta('generated'));
        await waitFor(() => expect(mockedGet).toHaveBeenCalled());
        expect(result.current.getViewCount('', 'missing.pdf')).toBe(0);
    });

    it('recordView 成功時にローカルの view_count / last_viewed_at が即時反映される', async () => {
        mockedGet.mockResolvedValue({});
        mockedPost.mockResolvedValue({ view_count: 1, last_viewed_at: 12345, incremented: true });

        const { result } = renderHook(() => useBookMeta('generated'));
        await waitFor(() => expect(mockedGet).toHaveBeenCalled());

        await act(async () => {
            await result.current.recordView('', 'book.pdf');
        });

        expect(mockedPost).toHaveBeenCalledWith('/api/meta/view', {
            path: '',
            name: 'book.pdf',
            source: 'generated',
        });
        expect(result.current.getViewCount('', 'book.pdf')).toBe(1);
        expect(result.current.getLastViewedAt('', 'book.pdf')).toBe(12345);
    });

    it('recordView は失敗を握りつぶす（throw しない）', async () => {
        mockedGet.mockResolvedValue({});
        mockedPost.mockRejectedValue(new Error('network down'));

        const { result } = renderHook(() => useBookMeta('generated'));
        await waitFor(() => expect(mockedGet).toHaveBeenCalled());

        await act(async () => {
            // throw しないことを期待
            await result.current.recordView('', 'book.pdf');
        });
        // ローカル状態は変化しない
        expect(result.current.getViewCount('', 'book.pdf')).toBe(0);
    });

    it('updateAuthors は view_count / last_viewed_at を保持する（バグ回帰防止）', async () => {
        mockedGet.mockResolvedValue({
            'book.pdf': { authors: ['古い作者'], view_count: 5, last_viewed_at: 999 },
        });
        mockedPatch.mockResolvedValue({ message: 'Updated', updated_count: 1 });

        const { result } = renderHook(() => useBookMeta('generated'));
        await waitFor(() => expect(mockedGet).toHaveBeenCalled());

        await act(async () => {
            await result.current.updateAuthors('', ['book.pdf'], ['新しい作者']);
        });

        // 作者は新規に置き換わるが、閲覧データは保持される
        expect(result.current.getAuthors('', 'book.pdf')).toEqual(['新しい作者']);
        expect(result.current.getViewCount('', 'book.pdf')).toBe(5);
        expect(result.current.getLastViewedAt('', 'book.pdf')).toBe(999);
    });

    it('updateAuthors で authors を空にしても view_count は残る', async () => {
        mockedGet.mockResolvedValue({
            'book.pdf': { authors: ['作者A'], view_count: 5, last_viewed_at: 999 },
        });
        mockedPatch.mockResolvedValue({ message: 'Updated', updated_count: 1 });

        const { result } = renderHook(() => useBookMeta('generated'));
        await waitFor(() => expect(mockedGet).toHaveBeenCalled());

        await act(async () => {
            await result.current.updateAuthors('', ['book.pdf'], []);
        });

        expect(result.current.getAuthors('', 'book.pdf')).toEqual([]);
        expect(result.current.getViewCount('', 'book.pdf')).toBe(5);
    });

    it('updateAuthors で authors も view_count も無いエントリは削除される', async () => {
        mockedGet.mockResolvedValue({
            'book.pdf': { authors: ['作者A'] },
        });
        mockedPatch.mockResolvedValue({ message: 'Updated', updated_count: 1 });

        const { result } = renderHook(() => useBookMeta('generated'));
        await waitFor(() => expect(mockedGet).toHaveBeenCalled());

        await act(async () => {
            await result.current.updateAuthors('', ['book.pdf'], []);
        });

        expect(result.current.meta['book.pdf']).toBeUndefined();
    });

    it('allAuthors は重複排除して日本語ソートで返す', async () => {
        mockedGet.mockResolvedValue({
            'a.pdf': { authors: ['さくらC', 'あさひA'] },
            'b.pdf': { authors: ['あさひA', 'かきくB'] },
        });

        const { result } = renderHook(() => useBookMeta('generated'));
        // GET 呼び出し後の状態反映を待つ
        await waitFor(() => expect(result.current.allAuthors.length).toBe(3));

        expect(result.current.allAuthors).toEqual(['あさひA', 'かきくB', 'さくらC']);
    });

    it('makeKey: path 有り/無しで区別される', async () => {
        mockedGet.mockResolvedValue({
            'book.pdf': { authors: ['ルート'] },
            'sub/book.pdf': { authors: ['サブ'] },
        });

        const { result } = renderHook(() => useBookMeta('generated'));
        await waitFor(() => expect(mockedGet).toHaveBeenCalled());

        expect(result.current.getAuthors('', 'book.pdf')).toEqual(['ルート']);
        expect(result.current.getAuthors('sub', 'book.pdf')).toEqual(['サブ']);
    });
});
