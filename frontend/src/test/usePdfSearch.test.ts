import { renderHook, act, waitFor } from '@testing-library/react';
import { vi, describe, it, expect } from 'vitest';
import { usePdfSearch } from '../hooks/usePdfSearch';

interface FakePage {
    getTextContent: () => Promise<{ items: Array<{ str: string }> }>;
}

interface FakePdf {
    numPages: number;
    getPage: (i: number) => Promise<FakePage>;
}

const buildPdf = (pages: string[]): FakePdf => ({
    numPages: pages.length,
    getPage: async (i: number) => ({
        getTextContent: async () => ({ items: [{ str: pages[i - 1] }] }),
    }),
});

describe('usePdfSearch', () => {
    it('初期状態は searchText 空 / matchCount=0 / currentMatch=0', () => {
        const setPage = vi.fn();
        const { result } = renderHook(() =>
            usePdfSearch({ isSearchOpen: false, setPageNumber: setPage }),
        );
        expect(result.current.searchText).toBe('');
        expect(result.current.matchCount).toBe(0);
        expect(result.current.currentMatch).toBe(0);
    });

    it('isSearchOpen=true + searchText で検索が走り、最初のヒットページに移動', async () => {
        const setPage = vi.fn();
        const { result } = renderHook(() =>
            usePdfSearch({ isSearchOpen: true, setPageNumber: setPage }),
        );

        // PDF をロード
        const pdf = buildPdf([
            'Page 1 has nothing',
            'Page 2 has hello world',
            'Page 3 also has hello here',
        ]);
        act(() => {
            // onDocumentLoaded で pdfRef を設定
            result.current.onDocumentLoaded(pdf as never);
        });

        // searchText を設定
        act(() => {
            result.current.setSearchText('hello');
        });

        await waitFor(() => expect(result.current.matchCount).toBe(2));
        expect(result.current.currentMatch).toBe(1);
        expect(setPage).toHaveBeenCalledWith(2);
    });

    it('大文字小文字を区別しない', async () => {
        const setPage = vi.fn();
        const { result } = renderHook(() =>
            usePdfSearch({ isSearchOpen: true, setPageNumber: setPage }),
        );

        const pdf = buildPdf(['HELLO World']);
        act(() => result.current.onDocumentLoaded(pdf as never));
        act(() => result.current.setSearchText('hello'));

        await waitFor(() => expect(result.current.matchCount).toBe(1));
    });

    it('正規表現特殊文字をエスケープして扱う', async () => {
        const setPage = vi.fn();
        const { result } = renderHook(() =>
            usePdfSearch({ isSearchOpen: true, setPageNumber: setPage }),
        );

        const pdf = buildPdf(['price (100) and (200)']);
        act(() => result.current.onDocumentLoaded(pdf as never));
        act(() => result.current.setSearchText('(100)'));

        await waitFor(() => expect(result.current.matchCount).toBe(1));
    });

    it('isSearchOpen=false なら matchCount は 0 にリセット', async () => {
        const setPage = vi.fn();
        const { result, rerender } = renderHook(
            ({ open }: { open: boolean }) =>
                usePdfSearch({ isSearchOpen: open, setPageNumber: setPage }),
            { initialProps: { open: true } },
        );

        const pdf = buildPdf(['hello world']);
        act(() => result.current.onDocumentLoaded(pdf as never));
        act(() => result.current.setSearchText('hello'));
        await waitFor(() => expect(result.current.matchCount).toBe(1));

        rerender({ open: false });
        await waitFor(() => expect(result.current.matchCount).toBe(0));
        expect(result.current.currentMatch).toBe(0);
    });

    it('searchText が空なら matchCount=0 で setPageNumber は呼ばれない', async () => {
        const setPage = vi.fn();
        const { result } = renderHook(() =>
            usePdfSearch({ isSearchOpen: true, setPageNumber: setPage }),
        );

        const pdf = buildPdf(['anything']);
        act(() => result.current.onDocumentLoaded(pdf as never));
        // setSearchText('') を明示
        act(() => result.current.setSearchText(''));

        await waitFor(() => expect(result.current.matchCount).toBe(0));
        expect(setPage).not.toHaveBeenCalled();
    });

    it('handleNextMatch で currentMatch が次へ進み、最後で 1 にラップする', async () => {
        const setPage = vi.fn();
        const { result } = renderHook(() =>
            usePdfSearch({ isSearchOpen: true, setPageNumber: setPage }),
        );

        const pdf = buildPdf(['a a a']); // 3 matches
        act(() => result.current.onDocumentLoaded(pdf as never));
        act(() => result.current.setSearchText('a'));
        await waitFor(() => expect(result.current.matchCount).toBe(3));

        act(() => result.current.handleNextMatch());
        expect(result.current.currentMatch).toBe(2);
        act(() => result.current.handleNextMatch());
        expect(result.current.currentMatch).toBe(3);
        act(() => result.current.handleNextMatch());
        expect(result.current.currentMatch).toBe(1); // ラップ
    });

    it('handlePrevMatch で currentMatch が戻り、1 で末尾にラップする', async () => {
        const setPage = vi.fn();
        const { result } = renderHook(() =>
            usePdfSearch({ isSearchOpen: true, setPageNumber: setPage }),
        );

        const pdf = buildPdf(['a a a']); // 3 matches
        act(() => result.current.onDocumentLoaded(pdf as never));
        act(() => result.current.setSearchText('a'));
        await waitFor(() => expect(result.current.matchCount).toBe(3));

        act(() => result.current.handlePrevMatch());
        expect(result.current.currentMatch).toBe(3); // 1 → matchCount にラップ
        act(() => result.current.handlePrevMatch());
        expect(result.current.currentMatch).toBe(2);
    });

    it('handleCloseSearch で searchText / match 系がリセットされる', async () => {
        const setPage = vi.fn();
        const { result } = renderHook(() =>
            usePdfSearch({ isSearchOpen: true, setPageNumber: setPage }),
        );

        const pdf = buildPdf(['hello world']);
        act(() => result.current.onDocumentLoaded(pdf as never));
        act(() => result.current.setSearchText('hello'));
        await waitFor(() => expect(result.current.matchCount).toBe(1));

        act(() => result.current.handleCloseSearch());
        expect(result.current.searchText).toBe('');
        expect(result.current.matchCount).toBe(0);
        expect(result.current.currentMatch).toBe(0);
    });

    it('customTextRenderer は searchText を <mark> でハイライトする', () => {
        const setPage = vi.fn();
        const { result } = renderHook(() =>
            usePdfSearch({ isSearchOpen: true, setPageNumber: setPage }),
        );
        act(() => result.current.setSearchText('cat'));

        const out = result.current.customTextRenderer({ str: 'a cat sat on the cat-mat' });
        expect(out).toContain('<mark');
        // "cat" 2 ヶ所のハイライト
        expect((out.match(/<mark/g) ?? []).length).toBe(2);
    });

    it('customTextRenderer: searchText 空ならそのまま str を返す', () => {
        const setPage = vi.fn();
        const { result } = renderHook(() =>
            usePdfSearch({ isSearchOpen: true, setPageNumber: setPage }),
        );
        const out = result.current.customTextRenderer({ str: 'plain text' });
        expect(out).toBe('plain text');
    });
});
