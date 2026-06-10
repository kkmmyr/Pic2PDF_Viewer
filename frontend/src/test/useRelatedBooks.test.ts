import { renderHook } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { useRelatedBooks } from '../hooks/reader/useRelatedBooks';
import type { BookMetaMap } from '../types';

describe('useRelatedBooks', () => {
    it('全 input が空なら 2 セクションすべて空', () => {
        const { result } = renderHook(() => useRelatedBooks({}, '', 'self.pdf'));
        expect(result.current).toEqual({ series: [], authors: [] });
    });

    it('自分自身は結果に含まれない', () => {
        const meta: BookMetaMap = {
            'self.pdf': {
                authors: ['A'],
                series_id: 's1',
                series_index: 1,
                series_title: 'シリーズ',
            },
        };
        const { result } = renderHook(() => useRelatedBooks(meta, '', 'self.pdf'));
        expect(result.current).toEqual({ series: [], authors: [] });
    });

    it('同シリーズは series_index 昇順、自分を除いて返す', () => {
        const meta: BookMetaMap = {
            'self.pdf': {
                authors: ['A'],
                series_id: 's1',
                series_index: 2,
                series_title: 'X',
            },
            'b.pdf': {
                authors: ['A'],
                series_id: 's1',
                series_index: 5,
                series_title: 'X',
            },
            'c.pdf': {
                authors: ['A'],
                series_id: 's1',
                series_index: 1,
                series_title: 'X',
            },
            'other.pdf': { authors: ['A'], series_id: 's2', series_index: 1 },
        };
        const { result } = renderHook(() => useRelatedBooks(meta, '', 'self.pdf'));
        expect(result.current.series.map((b) => b.name)).toEqual(['c.pdf', 'b.pdf']);
        expect(result.current.series[0]).toMatchObject({
            name: 'c.pdf',
            seriesIndex: 1,
            seriesTitle: 'X',
        });
    });

    it('同作者は authors 集合に少なくとも 1 人共通する書籍を返し、シリーズ済みを除く', () => {
        const meta: BookMetaMap = {
            'self.pdf': { authors: ['A', 'B'], series_id: 's1', series_index: 1 },
            'sameSeries.pdf': { authors: ['A'], series_id: 's1', series_index: 2 }, // series で消化
            'sameAuthor.pdf': { authors: ['A'] },
            'partialAuthor.pdf': { authors: ['B', 'C'] },
            'unrelated.pdf': { authors: ['Z'] },
        };
        const { result } = renderHook(() => useRelatedBooks(meta, '', 'self.pdf'));
        expect(result.current.series.map((b) => b.name)).toEqual(['sameSeries.pdf']);
        expect(result.current.authors.map((b) => b.name).sort()).toEqual([
            'partialAuthor.pdf',
            'sameAuthor.pdf',
        ]);
    });

    it('別フォルダの書籍は除外される', () => {
        const meta: BookMetaMap = {
            'self.pdf': { authors: ['A'] },
            'other.pdf': { authors: ['A'] },
            'sub/inAnotherFolder.pdf': { authors: ['A'] },
        };
        const { result } = renderHook(() => useRelatedBooks(meta, '', 'self.pdf'));
        expect(result.current.authors.map((b) => b.name)).toEqual(['other.pdf']);
    });

    it('currentPath 指定時はサブフォルダのみが対象になる', () => {
        const meta: BookMetaMap = {
            'sub/self.pdf': { authors: ['A'] },
            'sub/sibling.pdf': { authors: ['A'] },
            'self.pdf': { authors: ['A'] },
            'sub/deeper/nested.pdf': { authors: ['A'] },
        };
        const { result } = renderHook(() => useRelatedBooks(meta, 'sub', 'self.pdf'));
        expect(result.current.authors.map((b) => b.name)).toEqual(['sibling.pdf']);
    });

    it('シリーズ最大 8 件 / 作者最大 5 件で切る', () => {
        const meta: BookMetaMap = {
            'self.pdf': { authors: ['A'], series_id: 's1', series_index: 0 },
        };
        for (let i = 1; i <= 12; i++) {
            meta[`series${i}.pdf`] = {
                authors: ['A'],
                series_id: 's1',
                series_index: i,
            };
        }
        for (let i = 1; i <= 8; i++) {
            meta[`author${i}.pdf`] = { authors: ['A'] };
        }

        const { result } = renderHook(() => useRelatedBooks(meta, '', 'self.pdf'));
        expect(result.current.series).toHaveLength(8);
        expect(result.current.authors).toHaveLength(5);
    });

    it('currentPath サブフォルダで自分自身を除外', () => {
        const meta: BookMetaMap = {
            'sub/a.pdf': { authors: ['A'], series_id: 's1', series_index: 1 },
            'sub/b.pdf': { authors: ['A'], series_id: 's1', series_index: 2 },
        };
        const { result } = renderHook(() => useRelatedBooks(meta, 'sub', 'a.pdf'));
        expect(result.current.series.map((b) => b.name)).toEqual(['b.pdf']);
    });
});
