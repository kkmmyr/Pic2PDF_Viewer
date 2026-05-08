import { renderHook, act, waitFor } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';

vi.mock('../config/api_client', () => ({
    default: { get: vi.fn(), patch: vi.fn() },
}));

import apiClient from '../config/api_client';
import { useBookMetaCore } from '../hooks/useBookMetaCore';
import { useBookMetaWrite } from '../hooks/useBookMetaWrite';
import type { BookMetaMap } from '../types';

const mockedGet = apiClient.get as ReturnType<typeof vi.fn>;
const mockedPatch = apiClient.patch as ReturnType<typeof vi.fn>;

// Core + Write を組み合わせたヘルパー（実運用と同じ合成）
function useCombined(source: string) {
    const core = useBookMetaCore(source);
    const write = useBookMetaWrite(source, core.setMeta, core.makeKey);
    return { ...core, ...write };
}

const renderCombined = (initialMeta: BookMetaMap = {}) => {
    mockedGet.mockResolvedValue(initialMeta);
    return renderHook(() => useCombined('generated'));
};

describe('useBookMetaWrite', () => {
    beforeEach(() => {
        mockedGet.mockReset();
        mockedPatch.mockReset();
        mockedPatch.mockResolvedValue(undefined);
    });

    describe('updateAuthors', () => {
        it('PATCH を呼び、ローカル meta に authors が反映される', async () => {
            const { result } = renderCombined();
            await waitFor(() => expect(mockedGet).toHaveBeenCalled());

            await act(async () => {
                await result.current.updateAuthors('', ['a.pdf'], ['新作者']);
            });

            expect(mockedPatch).toHaveBeenCalledWith('/api/meta', {
                path: '',
                names: ['a.pdf'],
                authors: ['新作者'],
                source: 'generated',
            });
            expect(result.current.meta['a.pdf']?.authors).toEqual(['新作者']);
        });

        it('既存 view_count / last_viewed_at は保持される', async () => {
            const { result } = renderCombined({
                'a.pdf': { authors: ['古'], view_count: 5, last_viewed_at: 1000 },
            });
            await waitFor(() => expect(result.current.meta['a.pdf']).toBeDefined());

            await act(async () => {
                await result.current.updateAuthors('', ['a.pdf'], ['新']);
            });
            expect(result.current.meta['a.pdf']?.authors).toEqual(['新']);
            expect(result.current.meta['a.pdf']?.view_count).toBe(5);
            expect(result.current.meta['a.pdf']?.last_viewed_at).toBe(1000);
        });

        it('全フィールド空 + view_count 無しのエントリは meta から削除される', async () => {
            const { result } = renderCombined({ 'a.pdf': { authors: ['古'] } });
            await waitFor(() => expect(result.current.meta['a.pdf']).toBeDefined());

            await act(async () => {
                await result.current.updateAuthors('', ['a.pdf'], []);
            });
            expect(result.current.meta['a.pdf']).toBeUndefined();
        });

        it('view_count があれば authors 空でもエントリ保持', async () => {
            const { result } = renderCombined({ 'a.pdf': { authors: ['X'], view_count: 3 } });
            await waitFor(() => expect(result.current.meta['a.pdf']).toBeDefined());

            await act(async () => {
                await result.current.updateAuthors('', ['a.pdf'], []);
            });
            expect(result.current.meta['a.pdf']).toBeDefined();
            expect(result.current.meta['a.pdf']?.view_count).toBe(3);
        });
    });

    describe('updateGenre', () => {
        it('genre 文字列で merged.genre が設定される', async () => {
            const { result } = renderCombined();
            await waitFor(() => expect(mockedGet).toHaveBeenCalled());

            await act(async () => {
                await result.current.updateGenre('', ['a.pdf'], 'アクション');
            });
            expect(result.current.meta['a.pdf']?.genre).toBe('アクション');
        });

        it('genre="" で既存 genre が削除される', async () => {
            const { result } = renderCombined({
                'a.pdf': { authors: ['X'], genre: '旧ジャンル' },
            });
            await waitFor(() => expect(result.current.meta['a.pdf']).toBeDefined());

            await act(async () => {
                await result.current.updateGenre('', ['a.pdf'], '');
            });
            expect(result.current.meta['a.pdf']?.genre).toBeUndefined();
            // authors は保持
            expect(result.current.meta['a.pdf']?.authors).toEqual(['X']);
        });
    });

    describe('setHidden', () => {
        it('setHidden(true) で merged.hidden=true', async () => {
            const { result } = renderCombined({ 'a.pdf': { authors: ['X'] } });
            await waitFor(() => expect(result.current.meta['a.pdf']).toBeDefined());

            await act(async () => {
                await result.current.setHidden('', ['a.pdf'], true);
            });
            expect(result.current.meta['a.pdf']?.hidden).toBe(true);
        });

        it('setHidden(false) で hidden フィールドが削除される', async () => {
            const { result } = renderCombined({ 'a.pdf': { authors: ['X'], hidden: true } });
            await waitFor(() => expect(result.current.meta['a.pdf']?.hidden).toBe(true));

            await act(async () => {
                await result.current.setHidden('', ['a.pdf'], false);
            });
            expect(result.current.meta['a.pdf']?.hidden).toBeUndefined();
        });
    });

    describe('setReadState', () => {
        it('setReadState("done") で merged.read_state="done"', async () => {
            const { result } = renderCombined({ 'a.pdf': { authors: ['X'], view_count: 1 } });
            await waitFor(() => expect(result.current.meta['a.pdf']).toBeDefined());

            await act(async () => {
                await result.current.setReadState('', ['a.pdf'], 'done');
            });
            expect(result.current.meta['a.pdf']?.read_state).toBe('done');
            expect(mockedPatch).toHaveBeenCalledWith(
                '/api/meta',
                expect.objectContaining({
                    read_state: 'done',
                    names: ['a.pdf'],
                }),
            );
        });

        it('setReadState("") で read_state フィールドが削除される', async () => {
            const { result } = renderCombined({
                'a.pdf': { authors: ['X'], read_state: 'reading' },
            });
            await waitFor(() => expect(result.current.meta['a.pdf']?.read_state).toBe('reading'));

            await act(async () => {
                await result.current.setReadState('', ['a.pdf'], '');
            });
            expect(result.current.meta['a.pdf']?.read_state).toBeUndefined();
        });

        it('setReadState は authors / view_count 等を保持する', async () => {
            const { result } = renderCombined({
                'a.pdf': { authors: ['X'], view_count: 3, last_viewed_at: 12345 },
            });
            await waitFor(() => expect(result.current.meta['a.pdf']).toBeDefined());

            await act(async () => {
                await result.current.setReadState('', ['a.pdf'], 'reading');
            });
            expect(result.current.meta['a.pdf']).toMatchObject({
                authors: ['X'],
                view_count: 3,
                last_viewed_at: 12345,
                read_state: 'reading',
            });
        });
    });

    describe('updateMeta（直接呼び出し）', () => {
        it('全フィールド undefined だと no-op（PATCH 呼ばない）', async () => {
            const { result } = renderCombined();
            await waitFor(() => expect(mockedGet).toHaveBeenCalled());

            await act(async () => {
                await result.current.updateMeta('', ['a.pdf'], {});
            });
            expect(mockedPatch).not.toHaveBeenCalled();
        });

        it('複数フィールドを同時更新できる', async () => {
            const { result } = renderCombined();
            await waitFor(() => expect(mockedGet).toHaveBeenCalled());

            await act(async () => {
                await result.current.updateMeta('', ['a.pdf'], {
                    authors: ['X'],
                    genre: 'G',
                });
            });
            expect(result.current.meta['a.pdf']).toMatchObject({
                authors: ['X'],
                genre: 'G',
            });
        });

        it('複数 names を一度に更新できる', async () => {
            const { result } = renderCombined();
            await waitFor(() => expect(mockedGet).toHaveBeenCalled());

            await act(async () => {
                await result.current.updateMeta('', ['a.pdf', 'b.pdf'], { authors: ['同'] });
            });
            expect(result.current.meta['a.pdf']?.authors).toEqual(['同']);
            expect(result.current.meta['b.pdf']?.authors).toEqual(['同']);
        });

        it('path 指定で key が "{path}/{name}" になる', async () => {
            const { result } = renderCombined();
            await waitFor(() => expect(mockedGet).toHaveBeenCalled());

            await act(async () => {
                await result.current.updateMeta('sub', ['a.pdf'], { authors: ['Y'] });
            });
            expect(result.current.meta['sub/a.pdf']?.authors).toEqual(['Y']);
        });
    });
});
