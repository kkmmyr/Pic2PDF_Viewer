import { describe, it, expect } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useLibraryFilter } from '../hooks/useLibraryFilter';
import type { PdfFile, BookMetaMap } from '../types';

const makePdf = (name: string): PdfFile => ({
    name,
    thumbnail: null,
    created_at: 0,
});

describe('useLibraryFilter', () => {
    const pdfs: PdfFile[] = [
        makePdf('alpha.pdf'),
        makePdf('beta.pdf'),
        makePdf('gamma.pdf'),
    ];
    const directories = ['folder_one', 'folder_two', 'misc'];
    const meta: BookMetaMap = {
        'alpha.pdf':       { authors: ['サークルA'] },
        'beta.pdf':        { authors: ['サークルB'] },
        'gamma.pdf':       { authors: ['サークルA', 'サークルC'] },
        'sub/nested.pdf':  { authors: ['サークルD'] },
    };

    describe('searchText フィルター', () => {
        it('空文字列の場合は全件を返す', () => {
            const { result } = renderHook(() =>
                useLibraryFilter({ pdfs, directories, searchText: '', authorFilter: '', currentPath: '', meta })
            );
            expect(result.current.filteredPdfs).toHaveLength(3);
            expect(result.current.filteredDirs).toEqual(directories);
        });

        it('PDF 名で部分一致する書籍を返す', () => {
            const { result } = renderHook(() =>
                useLibraryFilter({ pdfs, directories, searchText: 'beta', authorFilter: '', currentPath: '', meta })
            );
            expect(result.current.filteredPdfs.map(p => p.name)).toEqual(['beta.pdf']);
        });

        it('大文字小文字を区別しない', () => {
            const { result } = renderHook(() =>
                useLibraryFilter({ pdfs, directories, searchText: 'ALPHA', authorFilter: '', currentPath: '', meta })
            );
            expect(result.current.filteredPdfs.map(p => p.name)).toEqual(['alpha.pdf']);
        });

        it('作者名でも検索ヒットする', () => {
            const { result } = renderHook(() =>
                useLibraryFilter({ pdfs, directories, searchText: 'サークルC', authorFilter: '', currentPath: '', meta })
            );
            expect(result.current.filteredPdfs.map(p => p.name)).toEqual(['gamma.pdf']);
        });

        it('フォルダ名にもフィルターを適用する', () => {
            const { result } = renderHook(() =>
                useLibraryFilter({ pdfs, directories, searchText: 'folder', authorFilter: '', currentPath: '', meta })
            );
            expect(result.current.filteredDirs).toEqual(['folder_one', 'folder_two']);
        });

        it('前後の空白はトリムされる', () => {
            const { result } = renderHook(() =>
                useLibraryFilter({ pdfs, directories, searchText: '   beta   ', authorFilter: '', currentPath: '', meta })
            );
            expect(result.current.filteredPdfs.map(p => p.name)).toEqual(['beta.pdf']);
        });
    });

    describe('authorFilter フィルター', () => {
        it('指定した作者を持つ書籍のみを返す', () => {
            const { result } = renderHook(() =>
                useLibraryFilter({ pdfs, directories, searchText: '', authorFilter: 'サークルA', currentPath: '', meta })
            );
            expect(result.current.filteredPdfs.map(p => p.name).sort()).toEqual(['alpha.pdf', 'gamma.pdf']);
        });

        it('完全一致のみ（部分一致しない）', () => {
            const { result } = renderHook(() =>
                useLibraryFilter({ pdfs, directories, searchText: '', authorFilter: 'サークル', currentPath: '', meta })
            );
            expect(result.current.filteredPdfs).toHaveLength(0);
        });

        it('searchText と AND で組み合わせる', () => {
            // searchText="alpha" + authorFilter="サークルA" → alpha.pdf のみ
            const { result } = renderHook(() =>
                useLibraryFilter({ pdfs, directories, searchText: 'alpha', authorFilter: 'サークルA', currentPath: '', meta })
            );
            expect(result.current.filteredPdfs.map(p => p.name)).toEqual(['alpha.pdf']);
        });
    });

    describe('showHidden（ゴミ箱モード）', () => {
        const pdfsWithHidden: PdfFile[] = [
            makePdf('visible.pdf'),
            makePdf('trashed.pdf'),
        ];
        const metaWithHidden: BookMetaMap = {
            'visible.pdf': { authors: ['A'] },
            'trashed.pdf': { authors: ['A'], hidden: true },
        };

        it('デフォルトは hidden を除外する', () => {
            const { result } = renderHook(() =>
                useLibraryFilter({
                    pdfs: pdfsWithHidden, directories: [],
                    searchText: '', authorFilter: '', currentPath: '', meta: metaWithHidden,
                })
            );
            expect(result.current.filteredPdfs.map(p => p.name)).toEqual(['visible.pdf']);
        });

        it('showHidden=true なら hidden のみを返す', () => {
            const { result } = renderHook(() =>
                useLibraryFilter({
                    pdfs: pdfsWithHidden, directories: [],
                    searchText: '', authorFilter: '', currentPath: '', meta: metaWithHidden,
                    showHidden: true,
                })
            );
            expect(result.current.filteredPdfs.map(p => p.name)).toEqual(['trashed.pdf']);
        });

        it('showHidden=false で明示的に通常モード', () => {
            const { result } = renderHook(() =>
                useLibraryFilter({
                    pdfs: pdfsWithHidden, directories: [],
                    searchText: '', authorFilter: '', currentPath: '', meta: metaWithHidden,
                    showHidden: false,
                })
            );
            expect(result.current.filteredPdfs.map(p => p.name)).toEqual(['visible.pdf']);
        });

        it('hidden 書籍は authorFilter からも除外される', () => {
            // 通常モードで作者 A で絞り込んでも hidden は出ない
            const { result } = renderHook(() =>
                useLibraryFilter({
                    pdfs: pdfsWithHidden, directories: [],
                    searchText: '', authorFilter: 'A', currentPath: '', meta: metaWithHidden,
                })
            );
            expect(result.current.filteredPdfs.map(p => p.name)).toEqual(['visible.pdf']);
        });
    });

    describe('seriesFilter（シリーズドリルダウン）', () => {
        const seriesPdfs: PdfFile[] = [
            makePdf('a1.pdf'),
            makePdf('a2.pdf'),
            makePdf('b1.pdf'),
        ];
        const seriesMeta: BookMetaMap = {
            'a1.pdf': { authors: ['A'], series_id: 'sid-a' },
            'a2.pdf': { authors: ['A'], series_id: 'sid-a' },
            'b1.pdf': { authors: ['B'], series_id: 'sid-b' },
        };

        it('seriesFilter で同じ series_id の書籍だけ表示する', () => {
            const { result } = renderHook(() =>
                useLibraryFilter({
                    pdfs: seriesPdfs, directories: [],
                    searchText: '', authorFilter: '', seriesFilter: 'sid-a',
                    currentPath: '', meta: seriesMeta,
                })
            );
            expect(result.current.filteredPdfs.map(p => p.name).sort()).toEqual(['a1.pdf', 'a2.pdf']);
        });

        it('空文字の seriesFilter は無効（フィルタしない）', () => {
            const { result } = renderHook(() =>
                useLibraryFilter({
                    pdfs: seriesPdfs, directories: [],
                    searchText: '', authorFilter: '', seriesFilter: '',
                    currentPath: '', meta: seriesMeta,
                })
            );
            expect(result.current.filteredPdfs).toHaveLength(3);
        });
    });

    describe('currentPath によるメタキー解決', () => {
        it('path 配下のメタを正しく取得する', () => {
            const sub = [makePdf('nested.pdf')];
            const { result } = renderHook(() =>
                useLibraryFilter({ pdfs: sub, directories: [], searchText: '', authorFilter: 'サークルD', currentPath: 'sub', meta })
            );
            expect(result.current.filteredPdfs.map(p => p.name)).toEqual(['nested.pdf']);
        });

        it('path 違いの作者では一致しない', () => {
            const sub = [makePdf('nested.pdf')];
            // currentPath="" のとき "nested.pdf" で引くが meta キーは "sub/nested.pdf" なのでヒットしない
            const { result } = renderHook(() =>
                useLibraryFilter({ pdfs: sub, directories: [], searchText: '', authorFilter: 'サークルD', currentPath: '', meta })
            );
            expect(result.current.filteredPdfs).toHaveLength(0);
        });
    });
});
