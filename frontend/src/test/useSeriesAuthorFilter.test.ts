import { renderHook } from '@testing-library/react';
import { vi, describe, it, expect } from 'vitest';
import { useSeriesAuthorFilter } from '../hooks/library/useSeriesAuthorFilter';
import type { BookMetaMap } from '../types';

const META: BookMetaMap = {
    'a.pdf': { series_id: 's1', authors: ['作者A'] },
    'b.pdf': { series_id: 's1', authors: ['作者A'] },
    'c.pdf': { series_id: 's2', authors: ['作者A'] },
    'd.pdf': { series_id: 's3', authors: ['作者B'] },
};

const ALL_SERIES = [
    { id: 's1', title: 'シリーズ1' },
    { id: 's2', title: 'シリーズ2' },
    { id: 's3', title: 'シリーズ3' },
];

const ALL_SERIES_STATS = [
    { id: 's1', title: 'シリーズ1', maxIndex: 1, count: 2 },
    { id: 's2', title: 'シリーズ2', maxIndex: 1, count: 1 },
    { id: 's3', title: 'シリーズ3', maxIndex: 1, count: 1 },
];

const getAuthors = (_path: string, name: string) => META[name]?.authors ?? [];

const setup = (overrides: Partial<Parameters<typeof useSeriesAuthorFilter>[0]> = {}) =>
    renderHook(() =>
        useSeriesAuthorFilter({
            meta: META,
            selectedItems: new Set(),
            getAuthors,
            currentPath: '',
            allSeries: ALL_SERIES,
            allSeriesWithStats: ALL_SERIES_STATS,
            seriesEditTarget: null,
            ...overrides,
        }),
    );

describe('useSeriesAuthorFilter', () => {
    describe('isMixedAuthors', () => {
        it('選択 0 件で false', () => {
            const { result } = setup();
            expect(result.current.isMixedAuthors).toBe(false);
        });

        it('同じ作者の選択で false', () => {
            const { result } = setup({ selectedItems: new Set(['a.pdf', 'b.pdf']) });
            expect(result.current.isMixedAuthors).toBe(false);
        });

        it('異なる作者を含む選択で true', () => {
            const { result } = setup({ selectedItems: new Set(['a.pdf', 'd.pdf']) });
            expect(result.current.isMixedAuthors).toBe(true);
        });

        it('PDF 以外（フォルダ）は判定対象外', () => {
            const { result } = setup({
                selectedItems: new Set(['a.pdf', 'someFolder']),
            });
            expect(result.current.isMixedAuthors).toBe(false);
        });
    });

    describe('validSeriesIdsByAuthorKey', () => {
        it('指定作者に属するシリーズ ID を返す', () => {
            const { result } = setup();
            const ids = result.current.validSeriesIdsByAuthorKey('作者A');
            expect(ids.has('s1')).toBe(true);
            expect(ids.has('s2')).toBe(true);
            expect(ids.has('s3')).toBe(false);
        });

        it('該当なしで空 Set', () => {
            const { result } = setup();
            const ids = result.current.validSeriesIdsByAuthorKey('未知の作者');
            expect(ids.size).toBe(0);
        });
    });

    describe('seriesEditFilteredSeries', () => {
        it('seriesEditTarget=null で全シリーズを返す', () => {
            const { result } = setup();
            expect(result.current.seriesEditFilteredSeries).toHaveLength(3);
        });

        it('対象書籍の作者で絞り込まれる', () => {
            const { result } = setup({ seriesEditTarget: 'a.pdf' });
            // a.pdf は 作者A なので s1 / s2 のみ
            const ids = result.current.seriesEditFilteredSeries.map((s) => s.id);
            expect(ids).toContain('s1');
            expect(ids).toContain('s2');
            expect(ids).not.toContain('s3');
        });

        it('対象書籍に作者が無ければ全シリーズを返す', () => {
            const getNoAuthors = vi.fn(() => []);
            const { result } = renderHook(() =>
                useSeriesAuthorFilter({
                    meta: META,
                    selectedItems: new Set(),
                    getAuthors: getNoAuthors,
                    currentPath: '',
                    allSeries: ALL_SERIES,
                    allSeriesWithStats: ALL_SERIES_STATS,
                    seriesEditTarget: 'a.pdf',
                }),
            );
            expect(result.current.seriesEditFilteredSeries).toHaveLength(3);
        });
    });

    describe('bulkSeriesFiltered', () => {
        it('mixed authors なら全シリーズを返す（フィルタしない）', () => {
            const { result } = setup({ selectedItems: new Set(['a.pdf', 'd.pdf']) });
            expect(result.current.bulkSeriesFiltered).toHaveLength(3);
        });

        it('単一作者の選択で対応シリーズに絞られる', () => {
            const { result } = setup({ selectedItems: new Set(['a.pdf', 'b.pdf']) });
            const ids = result.current.bulkSeriesFiltered.map((s) => s.id);
            expect(ids).toEqual(['s1', 's2']);
        });

        it('選択なしで全シリーズを返す', () => {
            const { result } = setup();
            expect(result.current.bulkSeriesFiltered).toHaveLength(3);
        });
    });
});
