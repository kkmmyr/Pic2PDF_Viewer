import { describe, it, expect } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useLibraryFilter } from '../hooks/library/useLibraryFilter';
import type { PdfFile, BookMetaMap } from '../types';

const makePdf = (name: string): PdfFile => ({
    name,
    thumbnail: null,
    created_at: 0,
});

describe('useLibraryFilter', () => {
    const pdfs: PdfFile[] = [makePdf('alpha.pdf'), makePdf('beta.pdf'), makePdf('gamma.pdf')];
    const meta: BookMetaMap = {
        'alpha.pdf': { authors: ['サークルA'] },
        'beta.pdf': { authors: ['サークルB'] },
        'gamma.pdf': { authors: ['サークルA', 'サークルC'] },
        'sub/nested.pdf': { authors: ['サークルD'] },
    };

    describe('searchText フィルター', () => {
        it('空文字列の場合は全件を返す', () => {
            const { result } = renderHook(() =>
                useLibraryFilter({ pdfs, searchText: '', authorFilter: '', currentPath: '', meta }),
            );
            expect(result.current.filteredPdfs).toHaveLength(3);
        });

        it('PDF 名で部分一致する書籍を返す', () => {
            const { result } = renderHook(() =>
                useLibraryFilter({
                    pdfs,
                    searchText: 'beta',
                    authorFilter: '',
                    currentPath: '',
                    meta,
                }),
            );
            expect(result.current.filteredPdfs.map((p) => p.name)).toEqual(['beta.pdf']);
        });

        it('大文字小文字を区別しない', () => {
            const { result } = renderHook(() =>
                useLibraryFilter({
                    pdfs,
                    searchText: 'ALPHA',
                    authorFilter: '',
                    currentPath: '',
                    meta,
                }),
            );
            expect(result.current.filteredPdfs.map((p) => p.name)).toEqual(['alpha.pdf']);
        });

        it('作者名でも検索ヒットする', () => {
            const { result } = renderHook(() =>
                useLibraryFilter({
                    pdfs,
                    searchText: 'サークルC',
                    authorFilter: '',
                    currentPath: '',
                    meta,
                }),
            );
            expect(result.current.filteredPdfs.map((p) => p.name)).toEqual(['gamma.pdf']);
        });

        it('前後の空白はトリムされる', () => {
            const { result } = renderHook(() =>
                useLibraryFilter({
                    pdfs,
                    searchText: '   beta   ',
                    authorFilter: '',
                    currentPath: '',
                    meta,
                }),
            );
            expect(result.current.filteredPdfs.map((p) => p.name)).toEqual(['beta.pdf']);
        });
    });

    describe('authorFilter フィルター', () => {
        it('指定した作者を持つ書籍のみを返す', () => {
            const { result } = renderHook(() =>
                useLibraryFilter({
                    pdfs,
                    searchText: '',
                    authorFilter: 'サークルA',
                    currentPath: '',
                    meta,
                }),
            );
            expect(result.current.filteredPdfs.map((p) => p.name).sort()).toEqual([
                'alpha.pdf',
                'gamma.pdf',
            ]);
        });

        it('完全一致のみ（部分一致しない）', () => {
            const { result } = renderHook(() =>
                useLibraryFilter({
                    pdfs,
                    searchText: '',
                    authorFilter: 'サークル',
                    currentPath: '',
                    meta,
                }),
            );
            expect(result.current.filteredPdfs).toHaveLength(0);
        });

        it('searchText と AND で組み合わせる', () => {
            // searchText="alpha" + authorFilter="サークルA" → alpha.pdf のみ
            const { result } = renderHook(() =>
                useLibraryFilter({
                    pdfs,
                    searchText: 'alpha',
                    authorFilter: 'サークルA',
                    currentPath: '',
                    meta,
                }),
            );
            expect(result.current.filteredPdfs.map((p) => p.name)).toEqual(['alpha.pdf']);
        });
    });

    describe('showHidden（ゴミ箱モード）', () => {
        const pdfsWithHidden: PdfFile[] = [makePdf('visible.pdf'), makePdf('trashed.pdf')];
        const metaWithHidden: BookMetaMap = {
            'visible.pdf': { authors: ['A'] },
            'trashed.pdf': { authors: ['A'], hidden: true },
        };

        it('デフォルトは hidden を除外する', () => {
            const { result } = renderHook(() =>
                useLibraryFilter({
                    pdfs: pdfsWithHidden,
                    searchText: '',
                    authorFilter: '',
                    currentPath: '',
                    meta: metaWithHidden,
                }),
            );
            expect(result.current.filteredPdfs.map((p) => p.name)).toEqual(['visible.pdf']);
        });

        it('showHidden=true なら hidden のみを返す', () => {
            const { result } = renderHook(() =>
                useLibraryFilter({
                    pdfs: pdfsWithHidden,
                    searchText: '',
                    authorFilter: '',
                    currentPath: '',
                    meta: metaWithHidden,
                    showHidden: true,
                }),
            );
            expect(result.current.filteredPdfs.map((p) => p.name)).toEqual(['trashed.pdf']);
        });

        it('showHidden=false で明示的に通常モード', () => {
            const { result } = renderHook(() =>
                useLibraryFilter({
                    pdfs: pdfsWithHidden,
                    searchText: '',
                    authorFilter: '',
                    currentPath: '',
                    meta: metaWithHidden,
                    showHidden: false,
                }),
            );
            expect(result.current.filteredPdfs.map((p) => p.name)).toEqual(['visible.pdf']);
        });

        it('hidden 書籍は authorFilter からも除外される', () => {
            // 通常モードで作者 A で絞り込んでも hidden は出ない
            const { result } = renderHook(() =>
                useLibraryFilter({
                    pdfs: pdfsWithHidden,
                    searchText: '',
                    authorFilter: 'A',
                    currentPath: '',
                    meta: metaWithHidden,
                }),
            );
            expect(result.current.filteredPdfs.map((p) => p.name)).toEqual(['visible.pdf']);
        });
    });

    describe('seriesFilter（シリーズドリルダウン）', () => {
        const seriesPdfs: PdfFile[] = [makePdf('a1.pdf'), makePdf('a2.pdf'), makePdf('b1.pdf')];
        const seriesMeta: BookMetaMap = {
            'a1.pdf': { authors: ['A'], series_id: 'sid-a' },
            'a2.pdf': { authors: ['A'], series_id: 'sid-a' },
            'b1.pdf': { authors: ['B'], series_id: 'sid-b' },
        };

        it('seriesFilter で同じ series_id の書籍だけ表示する', () => {
            const { result } = renderHook(() =>
                useLibraryFilter({
                    pdfs: seriesPdfs,
                    searchText: '',
                    authorFilter: '',
                    seriesFilter: 'sid-a',
                    currentPath: '',
                    meta: seriesMeta,
                }),
            );
            expect(result.current.filteredPdfs.map((p) => p.name).sort()).toEqual([
                'a1.pdf',
                'a2.pdf',
            ]);
        });

        it('空文字の seriesFilter は無効（フィルタしない）', () => {
            const { result } = renderHook(() =>
                useLibraryFilter({
                    pdfs: seriesPdfs,
                    searchText: '',
                    authorFilter: '',
                    seriesFilter: '',
                    currentPath: '',
                    meta: seriesMeta,
                }),
            );
            expect(result.current.filteredPdfs).toHaveLength(3);
        });
    });

    describe('currentPath によるメタキー解決', () => {
        it('path 配下のメタを正しく取得する', () => {
            const sub = [makePdf('nested.pdf')];
            const { result } = renderHook(() =>
                useLibraryFilter({
                    pdfs: sub,
                    searchText: '',
                    authorFilter: 'サークルD',
                    currentPath: 'sub',
                    meta,
                }),
            );
            expect(result.current.filteredPdfs.map((p) => p.name)).toEqual(['nested.pdf']);
        });

        it('path 違いの作者では一致しない', () => {
            const sub = [makePdf('nested.pdf')];
            // currentPath="" のとき "nested.pdf" で引くが meta キーは "sub/nested.pdf" なのでヒットしない
            const { result } = renderHook(() =>
                useLibraryFilter({
                    pdfs: sub,
                    searchText: '',
                    authorFilter: 'サークルD',
                    currentPath: '',
                    meta,
                }),
            );
            expect(result.current.filteredPdfs).toHaveLength(0);
        });
    });

    describe('追補: genreFilter / readStateFilter', () => {
        const genrePdfs: PdfFile[] = [
            makePdf('action.pdf'),
            makePdf('comedy.pdf'),
            makePdf('nogenre.pdf'),
        ];
        const genreMeta: BookMetaMap = {
            'action.pdf': { authors: ['A'], genre: 'アクション' },
            'comedy.pdf': { authors: ['A'], genre: 'コメディ' },
            'nogenre.pdf': { authors: ['A'] },
        };

        it('genreFilter で同ジャンルの書籍だけ表示', () => {
            const { result } = renderHook(() =>
                useLibraryFilter({
                    pdfs: genrePdfs,
                    searchText: '',
                    authorFilter: '',
                    genreFilter: 'アクション',
                    currentPath: '',
                    meta: genreMeta,
                }),
            );
            expect(result.current.filteredPdfs.map((p) => p.name)).toEqual(['action.pdf']);
        });

        it('genreFilter は他フィルタと AND 結合', () => {
            const { result } = renderHook(() =>
                useLibraryFilter({
                    pdfs: genrePdfs,
                    searchText: 'comedy',
                    authorFilter: '',
                    genreFilter: 'アクション',
                    currentPath: '',
                    meta: genreMeta,
                }),
            );
            expect(result.current.filteredPdfs).toHaveLength(0);
        });

        it('空文字 genreFilter は無効', () => {
            const { result } = renderHook(() =>
                useLibraryFilter({
                    pdfs: genrePdfs,
                    searchText: '',
                    authorFilter: '',
                    genreFilter: '',
                    currentPath: '',
                    meta: genreMeta,
                }),
            );
            expect(result.current.filteredPdfs).toHaveLength(3);
        });

        // read_state は派生 / 明示 / done の 3 ケース
        const stateFilterPdfs: PdfFile[] = [
            makePdf('a.pdf'), // 派生 unread (view_count=0)
            makePdf('b.pdf'), // 派生 reading (view_count>0)
            makePdf('c.pdf'), // 明示 done
            makePdf('d.pdf'), // 明示 unread (view_count>0 だが手動で unread）
        ];
        const stateFilterMeta: BookMetaMap = {
            'a.pdf': { authors: ['A'] },
            'b.pdf': { authors: ['A'], view_count: 3 },
            'c.pdf': { authors: ['A'], view_count: 7, read_state: 'done' },
            'd.pdf': { authors: ['A'], view_count: 1, read_state: 'unread' },
        };

        it('readStateFilter="unread" は派生 unread と明示 unread の両方を表示', () => {
            const { result } = renderHook(() =>
                useLibraryFilter({
                    pdfs: stateFilterPdfs,
                    searchText: '',
                    authorFilter: '',
                    currentPath: '',
                    meta: stateFilterMeta,
                    readStateFilter: 'unread',
                }),
            );
            expect(result.current.filteredPdfs.map((p) => p.name).sort()).toEqual([
                'a.pdf',
                'd.pdf',
            ]);
        });

        it('readStateFilter="reading" は派生 reading のみ', () => {
            const { result } = renderHook(() =>
                useLibraryFilter({
                    pdfs: stateFilterPdfs,
                    searchText: '',
                    authorFilter: '',
                    currentPath: '',
                    meta: stateFilterMeta,
                    readStateFilter: 'reading',
                }),
            );
            expect(result.current.filteredPdfs.map((p) => p.name)).toEqual(['b.pdf']);
        });

        it('readStateFilter="done" は明示 done のみ', () => {
            const { result } = renderHook(() =>
                useLibraryFilter({
                    pdfs: stateFilterPdfs,
                    searchText: '',
                    authorFilter: '',
                    currentPath: '',
                    meta: stateFilterMeta,
                    readStateFilter: 'done',
                }),
            );
            expect(result.current.filteredPdfs.map((p) => p.name)).toEqual(['c.pdf']);
        });

        it('readStateFilter="" （既定）はすべて表示', () => {
            const { result } = renderHook(() =>
                useLibraryFilter({
                    pdfs: stateFilterPdfs,
                    searchText: '',
                    authorFilter: '',
                    currentPath: '',
                    meta: stateFilterMeta,
                }),
            );
            expect(result.current.filteredPdfs).toHaveLength(4);
        });
    });
});
