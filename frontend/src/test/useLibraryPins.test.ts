import { renderHook, act } from '@testing-library/react';
import { describe, it, expect, beforeEach } from 'vitest';
import { useLibraryPins } from '../hooks/useLibraryPins';

beforeEach(() => {
    localStorage.clear();
});

describe('useLibraryPins', () => {
    describe('初期状態', () => {
        it('localStorage が空のとき seriesPins/authorPins は空オブジェクト', () => {
            const { result } = renderHook(() => useLibraryPins('doujin'));
            expect(result.current.seriesPins).toEqual({});
            expect(result.current.authorPins).toEqual({});
        });

        it('localStorage に既存データがあれば復元する', () => {
            localStorage.setItem('pins_series_doujin', JSON.stringify({ 'sid-1': 'vol3.pdf' }));
            localStorage.setItem(
                'pins_author_doujin',
                JSON.stringify({ 'Author A': 'bookA.pdf' }),
            );
            const { result } = renderHook(() => useLibraryPins('doujin'));
            expect(result.current.seriesPins).toEqual({ 'sid-1': 'vol3.pdf' });
            expect(result.current.authorPins).toEqual({ 'Author A': 'bookA.pdf' });
        });
    });

    describe('toggleSeriesPin', () => {
        it('未ピン状態でトグルするとピンが追加される', () => {
            const { result } = renderHook(() => useLibraryPins('doujin'));
            act(() => {
                result.current.toggleSeriesPin('sid-1', 'vol1.pdf');
            });
            expect(result.current.seriesPins['sid-1']).toBe('vol1.pdf');
        });

        it('同じ書籍を再トグルするとピンが解除される', () => {
            const { result } = renderHook(() => useLibraryPins('doujin'));
            act(() => {
                result.current.toggleSeriesPin('sid-1', 'vol1.pdf');
            });
            act(() => {
                result.current.toggleSeriesPin('sid-1', 'vol1.pdf');
            });
            expect(result.current.seriesPins['sid-1']).toBeUndefined();
        });

        it('別の書籍をトグルすると代表が切り替わる（1グループ1冊のみ）', () => {
            const { result } = renderHook(() => useLibraryPins('doujin'));
            act(() => {
                result.current.toggleSeriesPin('sid-1', 'vol1.pdf');
            });
            act(() => {
                result.current.toggleSeriesPin('sid-1', 'vol3.pdf');
            });
            expect(result.current.seriesPins['sid-1']).toBe('vol3.pdf');
        });

        it('localStorage に保存される', () => {
            const { result } = renderHook(() => useLibraryPins('doujin'));
            act(() => {
                result.current.toggleSeriesPin('sid-1', 'vol2.pdf');
            });
            const stored = JSON.parse(localStorage.getItem('pins_series_doujin') ?? '{}');
            expect(stored['sid-1']).toBe('vol2.pdf');
        });

        it('シリーズピンは作者ピンに影響しない', () => {
            const { result } = renderHook(() => useLibraryPins('doujin'));
            act(() => {
                result.current.toggleSeriesPin('sid-1', 'vol1.pdf');
            });
            expect(result.current.authorPins).toEqual({});
        });
    });

    describe('toggleAuthorPin', () => {
        it('未ピン状態でトグルするとピンが追加される', () => {
            const { result } = renderHook(() => useLibraryPins('doujin'));
            act(() => {
                result.current.toggleAuthorPin('Author A\nAuthor B', 'bookA.pdf');
            });
            expect(result.current.authorPins['Author A\nAuthor B']).toBe('bookA.pdf');
        });

        it('同じ書籍を再トグルするとピンが解除される', () => {
            const { result } = renderHook(() => useLibraryPins('doujin'));
            act(() => {
                result.current.toggleAuthorPin('Author A', 'bookA.pdf');
            });
            act(() => {
                result.current.toggleAuthorPin('Author A', 'bookA.pdf');
            });
            expect(result.current.authorPins['Author A']).toBeUndefined();
        });

        it('別の書籍をトグルすると代表が切り替わる', () => {
            const { result } = renderHook(() => useLibraryPins('doujin'));
            act(() => {
                result.current.toggleAuthorPin('Author A', 'bookA.pdf');
            });
            act(() => {
                result.current.toggleAuthorPin('Author A', 'bookB.pdf');
            });
            expect(result.current.authorPins['Author A']).toBe('bookB.pdf');
        });

        it('localStorage に保存される', () => {
            const { result } = renderHook(() => useLibraryPins('doujin'));
            act(() => {
                result.current.toggleAuthorPin('Author A', 'bookA.pdf');
            });
            const stored = JSON.parse(localStorage.getItem('pins_author_doujin') ?? '{}');
            expect(stored['Author A']).toBe('bookA.pdf');
        });

        it('作者ピンはシリーズピンに影響しない', () => {
            const { result } = renderHook(() => useLibraryPins('doujin'));
            act(() => {
                result.current.toggleAuthorPin('Author A', 'bookA.pdf');
            });
            expect(result.current.seriesPins).toEqual({});
        });
    });

    describe('ソース別の独立管理', () => {
        it('source が異なれば別のキーで管理される', () => {
            const { result: gen } = renderHook(() => useLibraryPins('doujin'));
            const { result: kin } = renderHook(() => useLibraryPins('comic'));
            act(() => {
                gen.current.toggleSeriesPin('sid-1', 'vol1.pdf');
            });
            expect(kin.current.seriesPins).toEqual({});
            expect(localStorage.getItem('pins_series_comic')).toBeNull();
        });
    });
});
