import { renderHook } from '@testing-library/react';
import { vi, describe, it, expect } from 'vitest';
import { useLibraryDisplay } from '../hooks/library/useLibraryDisplay';
import type { PdfFile, BookMetaMap } from '../types';

const pdf = (name: string): PdfFile => ({ name, thumbnail: null, created_at: 0 });

const META: BookMetaMap = {
    'a.pdf': { series_id: 's1', series_title: 'シリーズX', series_index: 2, authors: ['作者A'] },
    'b.pdf': { series_id: 's1', series_title: 'シリーズX', series_index: 1, authors: ['作者A'] },
    'c.pdf': { authors: ['作者B'] },
};

const getSeries = (_path: string, name: string) => {
    const e = META[name];
    if (!e?.series_id || e.series_index === undefined) return null;
    return { id: e.series_id, index: e.series_index, title: e.series_title ?? '' };
};

const setup = (overrides: Partial<Parameters<typeof useLibraryDisplay>[0]> = {}) =>
    renderHook(() =>
        useLibraryDisplay({
            filteredPdfs: [pdf('a.pdf'), pdf('b.pdf'), pdf('c.pdf')],
            meta: META,
            currentPath: '',
            groupMode: 'none',
            authorFilter: '',
            seriesFilter: '',
            getSeries,
            clearAllDrilldown: vi.fn(),
            setSeriesFilter: vi.fn(),
            ...overrides,
        }),
    );

describe('useLibraryDisplay', () => {
    describe('effectiveGroupMode', () => {
        it('seriesFilter があれば none', () => {
            const { result } = setup({ seriesFilter: 's1', groupMode: 'series' });
            expect(result.current.effectiveGroupMode).toBe('none');
        });

        it('authorFilter のみで non-author-then-series mode は none', () => {
            const { result } = setup({ authorFilter: 'A', groupMode: 'series' });
            expect(result.current.effectiveGroupMode).toBe('none');
        });

        it('groupMode=author-then-series + authorFilter なし → author', () => {
            const { result } = setup({ groupMode: 'author-then-series' });
            expect(result.current.effectiveGroupMode).toBe('author');
        });

        it('groupMode=author-then-series + authorFilter あり → series', () => {
            const { result } = setup({
                groupMode: 'author-then-series',
                authorFilter: '作者A',
            });
            expect(result.current.effectiveGroupMode).toBe('series');
        });

        it('groupMode=none / filter なし → そのまま', () => {
            const { result } = setup();
            expect(result.current.effectiveGroupMode).toBe('none');
        });
    });

    describe('displayPdfs', () => {
        it('seriesFilter なしなら grouped.items そのまま', () => {
            const { result } = setup();
            expect(result.current.displayPdfs.map((p) => p.name)).toEqual([
                'a.pdf',
                'b.pdf',
                'c.pdf',
            ]);
        });

        it('seriesFilter ありなら series_index 昇順で並び替え', () => {
            const { result } = setup({
                seriesFilter: 's1',
                filteredPdfs: [pdf('a.pdf'), pdf('b.pdf')],
            });
            // a.pdf=index 2, b.pdf=index 1 → b.pdf, a.pdf
            expect(result.current.displayPdfs.map((p) => p.name)).toEqual(['b.pdf', 'a.pdf']);
        });
    });

    describe('breadcrumbs', () => {
        it('filter なしで空配列', () => {
            const { result } = setup();
            expect(result.current.breadcrumbs).toEqual([]);
        });

        it('authorFilter のみ → ライブラリ + 作者', () => {
            const { result } = setup({ authorFilter: '作者A' });
            expect(result.current.breadcrumbs).toHaveLength(2);
            expect(result.current.breadcrumbs[0].kind).toBe('home');
            expect(result.current.breadcrumbs[1].kind).toBe('author');
            expect(result.current.breadcrumbs[1].label).toBe('作者A');
            expect(result.current.breadcrumbs[1].onClick).toBeUndefined(); // series なしならクリック不可
        });

        it('seriesFilter ありで series 階層が追加され、series_title を引いて表示', () => {
            const { result } = setup({ seriesFilter: 's1', authorFilter: '作者A' });
            expect(result.current.breadcrumbs).toHaveLength(3);
            expect(result.current.breadcrumbs[2].kind).toBe('series');
            expect(result.current.breadcrumbs[2].label).toBe('シリーズX');
            // author 階層は series ありならクリック可
            expect(result.current.breadcrumbs[1].onClick).toBeDefined();
        });

        it('seriesFilter のみ（authorFilter なし）でも series 階層が表示', () => {
            const { result } = setup({ seriesFilter: 's1' });
            const labels = result.current.breadcrumbs.map((c) => c.kind);
            expect(labels).toEqual(['home', 'series']);
        });

        it('breadcrumbs の home クリックで clearAllDrilldown が呼ばれる', () => {
            const clearAllDrilldown = vi.fn();
            const { result } = setup({ authorFilter: 'A', clearAllDrilldown });
            result.current.breadcrumbs[0].onClick?.();
            expect(clearAllDrilldown).toHaveBeenCalled();
        });

        it('series 階層がある状態の author 階層クリックで setSeriesFilter("") が呼ばれる', () => {
            const setSeriesFilter = vi.fn();
            const { result } = setup({
                authorFilter: 'A',
                seriesFilter: 's1',
                setSeriesFilter,
            });
            result.current.breadcrumbs[1].onClick?.();
            expect(setSeriesFilter).toHaveBeenCalledWith('');
        });
    });
});
