import { renderHook, act, waitFor } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';

vi.mock('../config/api_client', () => ({
    default: { post: vi.fn() },
}));

import apiClient from '../config/api_client';
import { useSeriesSuggestion } from '../hooks/useSeriesSuggestion';

const mockedPost = apiClient.post as ReturnType<typeof vi.fn>;

describe('useSeriesSuggestion', () => {
    beforeEach(() => {
        mockedPost.mockReset();
    });

    it('初期状態は candidates=[] / loading=false / error=null', () => {
        const { result } = renderHook(() => useSeriesSuggestion('generated', ''));
        expect(result.current.candidates).toEqual([]);
        expect(result.current.loading).toBe(false);
        expect(result.current.error).toBeNull();
    });

    it('fetchSuggestions(空配列) は何もせず candidates をクリア', async () => {
        const { result } = renderHook(() => useSeriesSuggestion('generated', ''));
        await act(async () => {
            await result.current.fetchSuggestions([]);
        });
        expect(result.current.candidates).toEqual([]);
        expect(mockedPost).not.toHaveBeenCalled();
    });

    it('fetchSuggestions 成功で候補が入る', async () => {
        mockedPost.mockResolvedValue({
            candidates: [
                {
                    series_id: 's1',
                    series_title: '鬼滅の刃',
                    series_max_index: 5,
                    score: 0.85,
                    reason: 'title_match,author_match',
                },
            ],
        });
        const { result } = renderHook(() => useSeriesSuggestion('generated', 'sub'));
        await act(async () => {
            await result.current.fetchSuggestions(['鬼滅の刃 6.pdf']);
        });
        await waitFor(() => expect(result.current.candidates).toHaveLength(1));
        expect(result.current.candidates[0].series_id).toBe('s1');
        expect(mockedPost).toHaveBeenCalledWith('/api/series/suggest', {
            path: 'sub',
            names: ['鬼滅の刃 6.pdf'],
            source: 'generated',
        });
    });

    it('fetchSuggestions 失敗で error がセットされ candidates は空', async () => {
        mockedPost.mockRejectedValue(new Error('boom'));
        const { result } = renderHook(() => useSeriesSuggestion('generated', ''));
        await act(async () => {
            await result.current.fetchSuggestions(['a.pdf']);
        });
        expect(result.current.error).toBe('boom');
        expect(result.current.candidates).toEqual([]);
    });

    it('reset で candidates と error をクリア', async () => {
        mockedPost.mockResolvedValue({
            candidates: [
                {
                    series_id: 's1',
                    series_title: 'X',
                    series_max_index: 1,
                    score: 0.5,
                    reason: 'title_match',
                },
            ],
        });
        const { result } = renderHook(() => useSeriesSuggestion('generated', ''));
        await act(async () => {
            await result.current.fetchSuggestions(['a.pdf']);
        });
        expect(result.current.candidates).toHaveLength(1);

        act(() => {
            result.current.reset();
        });
        expect(result.current.candidates).toEqual([]);
        expect(result.current.error).toBeNull();
    });

    it('レスポンスに candidates が無くても [] にフォールバック', async () => {
        mockedPost.mockResolvedValue({});
        const { result } = renderHook(() => useSeriesSuggestion('generated', ''));
        await act(async () => {
            await result.current.fetchSuggestions(['a.pdf']);
        });
        expect(result.current.candidates).toEqual([]);
        expect(result.current.error).toBeNull();
    });
});
