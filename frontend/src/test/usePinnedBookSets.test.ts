import { renderHook } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { usePinnedBookSets } from '../hooks/usePinnedBookSets';
import type { BookMetaMap } from '../types';

const META: BookMetaMap = {
    'a.pdf': { series_id: 's1', authors: ['作者A'] },
    'b.pdf': { series_id: 's1', authors: ['作者A'] },
    'c.pdf': { authors: ['作者B'] },
    'sub/x.pdf': { series_id: 's2', authors: ['作者C'] },
};

describe('usePinnedBookSets', () => {
    it('seriesPins / authorPins 両方空なら pinnedBooks も空', () => {
        const { result } = renderHook(() =>
            usePinnedBookSets({
                meta: META,
                currentPath: '',
                seriesPins: {},
                authorPins: {},
                authorFilter: '',
                seriesFilter: '',
            }),
        );
        expect(result.current.pinnedBooks.size).toBe(0);
    });

    it('seriesPins で指定された name が pinnedBooks に入る', () => {
        const { result } = renderHook(() =>
            usePinnedBookSets({
                meta: META,
                currentPath: '',
                seriesPins: { s1: 'a.pdf' },
                authorPins: {},
                authorFilter: '',
                seriesFilter: '',
            }),
        );
        expect(result.current.pinnedBooks.has('a.pdf')).toBe(true);
        expect(result.current.pinnedBooks.has('b.pdf')).toBe(false);
    });

    it('authorPins で指定された name も pinnedBooks に入る', () => {
        const { result } = renderHook(() =>
            usePinnedBookSets({
                meta: META,
                currentPath: '',
                seriesPins: {},
                authorPins: { 作者B: 'c.pdf' },
                authorFilter: '',
                seriesFilter: '',
            }),
        );
        expect(result.current.pinnedBooks.has('c.pdf')).toBe(true);
    });

    it('別フォルダ（同 currentPath 直下でない）はスキップ', () => {
        const { result } = renderHook(() =>
            usePinnedBookSets({
                meta: META,
                currentPath: '',
                seriesPins: { s2: 'x.pdf' }, // sub/x.pdf は currentPath="" の直下ではない
                authorPins: {},
                authorFilter: '',
                seriesFilter: '',
            }),
        );
        expect(result.current.pinnedBooks.has('x.pdf')).toBe(false);
    });

    it('currentPath="sub" でサブフォルダのピンが認識される', () => {
        const { result } = renderHook(() =>
            usePinnedBookSets({
                meta: META,
                currentPath: 'sub',
                seriesPins: { s2: 'x.pdf' },
                authorPins: {},
                authorFilter: '',
                seriesFilter: '',
            }),
        );
        expect(result.current.pinnedBooks.has('x.pdf')).toBe(true);
    });

    it('contextualFavorites: filter なしなら空', () => {
        const { result } = renderHook(() =>
            usePinnedBookSets({
                meta: META,
                currentPath: '',
                seriesPins: { s1: 'a.pdf' },
                authorPins: { 作者B: 'c.pdf' },
                authorFilter: '',
                seriesFilter: '',
            }),
        );
        expect(result.current.contextualFavorites.size).toBe(0);
    });

    it('contextualFavorites: seriesFilter 中はシリーズピンのみ', () => {
        const { result } = renderHook(() =>
            usePinnedBookSets({
                meta: META,
                currentPath: '',
                seriesPins: { s1: 'a.pdf' },
                authorPins: { 作者B: 'c.pdf' },
                authorFilter: '',
                seriesFilter: 's1',
            }),
        );
        expect(result.current.contextualFavorites.has('a.pdf')).toBe(true);
        expect(result.current.contextualFavorites.has('c.pdf')).toBe(false);
    });

    it('contextualFavorites: authorFilter のみ中は作者ピンのみ', () => {
        const { result } = renderHook(() =>
            usePinnedBookSets({
                meta: META,
                currentPath: '',
                seriesPins: { s1: 'a.pdf' },
                authorPins: { 作者B: 'c.pdf' },
                authorFilter: '作者B',
                seriesFilter: '',
            }),
        );
        expect(result.current.contextualFavorites.has('c.pdf')).toBe(true);
        expect(result.current.contextualFavorites.has('a.pdf')).toBe(false);
    });
});
