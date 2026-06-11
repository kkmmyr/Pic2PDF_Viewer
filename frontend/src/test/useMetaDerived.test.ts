import { renderHook } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { useMetaDerived } from '@/hooks/library/useMetaDerived';
import type { BookMetaMap } from '@/types';

describe('useMetaDerived', () => {
    it('空 meta なら全派生値が空', () => {
        const { result } = renderHook(() => useMetaDerived({}));
        expect(result.current.allAuthors).toEqual([]);
        expect(result.current.allGenres).toEqual([]);
        expect(result.current.allSeries).toEqual([]);
        expect(result.current.allSeriesWithStats).toEqual([]);
    });

    it('allAuthors は重複排除 + cmpJa 順', () => {
        const meta: BookMetaMap = {
            'a.pdf': { authors: ['さくら', 'あさひ'] },
            'b.pdf': { authors: ['あさひ', 'かきく'] },
        };
        const { result } = renderHook(() => useMetaDerived(meta));
        expect(result.current.allAuthors).toEqual(['あさひ', 'かきく', 'さくら']);
    });

    it('authors 不在エントリは無視される（undefined 混入なし）', () => {
        const meta: BookMetaMap = {
            'a.pdf': { authors: ['A'] },
            'b.pdf': {}, // authors 欠落
            'c.pdf': { authors: ['B'] },
        };
        const { result } = renderHook(() => useMetaDerived(meta));
        expect(result.current.allAuthors).toEqual(['A', 'B']);
    });

    it('allGenres は falsy 値（undefined / 空文字）を除外', () => {
        const meta: BookMetaMap = {
            'a.pdf': { genre: 'アクション' },
            'b.pdf': { genre: '' }, // 空文字 → 除外
            'c.pdf': {}, // 不在 → 除外
            'd.pdf': { genre: 'コメディ' },
        };
        const { result } = renderHook(() => useMetaDerived(meta));
        expect(result.current.allGenres).toEqual(['アクション', 'コメディ']);
    });

    it('allSeries は同 series_id を 1 つに集約してタイトル順', () => {
        const meta: BookMetaMap = {
            'a.pdf': { series_id: 's1', series_title: 'B シリーズ' },
            'b.pdf': { series_id: 's1', series_title: 'B シリーズ' },
            'c.pdf': { series_id: 's2', series_title: 'A シリーズ' },
        };
        const { result } = renderHook(() => useMetaDerived(meta));
        expect(result.current.allSeries).toEqual([
            { id: 's2', title: 'A シリーズ' },
            { id: 's1', title: 'B シリーズ' },
        ]);
    });

    it('series_title 欠落でも空文字としてエントリされる', () => {
        const meta: BookMetaMap = {
            'a.pdf': { series_id: 's1' }, // series_title 不在
        };
        const { result } = renderHook(() => useMetaDerived(meta));
        expect(result.current.allSeries).toEqual([{ id: 's1', title: '' }]);
    });

    it('allSeriesWithStats は count と maxIndex を集計する', () => {
        const meta: BookMetaMap = {
            'v1.pdf': { series_id: 's1', series_title: 'X', series_index: 1 },
            'v2.pdf': { series_id: 's1', series_title: 'X', series_index: 2 },
            'v3.pdf': { series_id: 's1', series_title: 'X', series_index: 3 },
            'y1.pdf': { series_id: 's2', series_title: 'Y', series_index: 1 },
        };
        const { result } = renderHook(() => useMetaDerived(meta));
        expect(result.current.allSeriesWithStats).toEqual([
            { id: 's1', title: 'X', maxIndex: 3, count: 3 },
            { id: 's2', title: 'Y', maxIndex: 1, count: 1 },
        ]);
    });

    it('series_index 欠落のエントリは maxIndex=0 として扱う', () => {
        const meta: BookMetaMap = {
            'a.pdf': { series_id: 's1', series_title: 'A' },
        };
        const { result } = renderHook(() => useMetaDerived(meta));
        expect(result.current.allSeriesWithStats[0].maxIndex).toBe(0);
        expect(result.current.allSeriesWithStats[0].count).toBe(1);
    });

    it('series_id 不在のエントリは allSeries / allSeriesWithStats に含まれない', () => {
        const meta: BookMetaMap = {
            'a.pdf': { authors: ['X'] }, // series 関連なし
            'b.pdf': { series_id: 's1', series_title: 'X' },
        };
        const { result } = renderHook(() => useMetaDerived(meta));
        expect(result.current.allSeries).toHaveLength(1);
        expect(result.current.allSeriesWithStats).toHaveLength(1);
    });
});
