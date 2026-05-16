import { renderHook } from '@testing-library/react';
import { describe, it, expect } from 'vitest';

import { useNovelLibraryGroup } from '../hooks/useNovelLibraryGroup';
import type { BookSummary } from '../features/novel_db/types';

const book = (
    name: string,
    authors: string[] = [],
    series_id: string | null = null,
    series_title: string | null = null,
    volume: number | null = null,
): BookSummary => ({
    name,
    authors,
    series_id,
    series_title,
    is_indexed: false,
    page_count: null,
    indexed_at: null,
    thumbnail_url: null,
    ocr_done_at: null,
    volume,
    publisher: null,
    asin: null,
    series_index: null,
});

const A = book('bookA', ['作者A'], 's1', 'シリーズ1', 1);
const B = book('bookB', ['作者A'], 's1', 'シリーズ1', 2);
const C = book('bookC', ['作者B'], 's2', 'シリーズ2', 1);
const D = book('bookD', [], null, null, null); // 作者・シリーズ未設定
const E = book('bookE', ['作者A'], null, null, null); // 作者あり・シリーズなし
const F = book('bookF', [], 's1', 'シリーズ1', 3); // 作者なし・シリーズあり

describe('useNovelLibraryGroup', () => {
    describe('flat モード', () => {
        it('全書籍が ungrouped に入り groups は空', () => {
            const { result } = renderHook(() => useNovelLibraryGroup([A, B, C, D], 'flat'));
            expect(result.current.groups).toHaveLength(0);
            expect(result.current.ungrouped).toHaveLength(4);
        });
    });

    describe('author モード', () => {
        it('第 1 作者でグループ化される', () => {
            const { result } = renderHook(() => useNovelLibraryGroup([A, B, C], 'author'));
            const { groups, ungrouped } = result.current;
            expect(ungrouped).toHaveLength(0);
            expect(groups).toHaveLength(2);
            const authorA = groups.find((g) => g.label === '作者A');
            expect(authorA?.books).toHaveLength(2);
        });

        it('作者未設定の書籍は ungrouped に入る', () => {
            const { result } = renderHook(() => useNovelLibraryGroup([A, D], 'author'));
            expect(result.current.ungrouped).toContainEqual(D);
            expect(result.current.groups.flatMap((g) => g.books)).not.toContainEqual(D);
        });

        it('グループはラベル昇順でソートされる', () => {
            const { result } = renderHook(() => useNovelLibraryGroup([C, A], 'author'));
            const labels = result.current.groups.map((g) => g.label);
            expect(labels).toEqual([...labels].sort());
        });
    });

    describe('series モード', () => {
        it('series_id でグループ化される', () => {
            const { result } = renderHook(() => useNovelLibraryGroup([A, B, C], 'series'));
            const { groups } = result.current;
            expect(groups).toHaveLength(2);
            const s1 = groups.find((g) => g.label === 'シリーズ1');
            expect(s1?.books).toHaveLength(2);
        });

        it('シリーズ内は volume 昇順にソートされる', () => {
            const bVol3 = book('bookB3', ['作者A'], 's1', 'シリーズ1', 3);
            const bVol1 = book('bookB1', ['作者A'], 's1', 'シリーズ1', 1);
            const { result } = renderHook(() => useNovelLibraryGroup([bVol3, bVol1], 'series'));
            const s1 = result.current.groups[0];
            expect(s1.books[0].volume).toBe(1);
            expect(s1.books[1].volume).toBe(3);
        });

        it('volume が null の書籍はシリーズ末尾に入る', () => {
            const bNull = book('bookNull', ['作者A'], 's1', 'シリーズ1', null);
            const bVol1 = book('bookVol1', ['作者A'], 's1', 'シリーズ1', 1);
            const { result } = renderHook(() => useNovelLibraryGroup([bNull, bVol1], 'series'));
            const s1 = result.current.groups[0];
            expect(s1.books[0]).toBe(bVol1);
            expect(s1.books[1]).toBe(bNull);
        });

        it('シリーズ未設定の書籍は ungrouped に入る', () => {
            const { result } = renderHook(() => useNovelLibraryGroup([A, D, E], 'series'));
            expect(result.current.ungrouped).toContainEqual(D);
            expect(result.current.ungrouped).toContainEqual(E);
        });

        it('作者なし・シリーズあり書籍はグループに入る', () => {
            const { result } = renderHook(() => useNovelLibraryGroup([F], 'series'));
            expect(result.current.groups).toHaveLength(1);
            expect(result.current.ungrouped).toHaveLength(0);
        });
    });
});
