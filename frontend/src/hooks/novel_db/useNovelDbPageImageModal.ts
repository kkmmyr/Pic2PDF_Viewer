/**
 * 画像モーダルの開閉 + 前後ページ送りフック。
 */
import { useCallback, useEffect, useState } from 'react';

import type { BookSummary } from '../../features/novel_db/types';

export interface ImageModalState {
    book: string;
    pageNo: number;
}

export interface UseNovelDbPageImageModal {
    state: ImageModalState | null;
    open: (book: string, pageNo: number) => void;
    close: () => void;
    prevPage: () => void;
    nextPage: () => void;
    /** 開いている書籍のページ数（末尾判定用）。書籍が無ければ 0。 */
    maxPage: number;
}

export function useNovelDbPageImageModal(books: BookSummary[]): UseNovelDbPageImageModal {
    const [state, setState] = useState<ImageModalState | null>(null);

    const maxPage = (state && books.find((b) => b.name === state.book)?.page_count) || 0;

    const open = useCallback((book: string, pageNo: number) => {
        setState({ book, pageNo });
    }, []);

    const close = useCallback(() => setState(null), []);

    const prevPage = useCallback(() => {
        setState((prev) => (prev && prev.pageNo > 1 ? { ...prev, pageNo: prev.pageNo - 1 } : prev));
    }, []);

    const nextPage = useCallback(() => {
        setState((prev) => {
            if (!prev) return prev;
            const m = books.find((b) => b.name === prev.book)?.page_count ?? 0;
            return prev.pageNo < m ? { ...prev, pageNo: prev.pageNo + 1 } : prev;
        });
    }, [books]);

    // キーボード操作: 左右で前後送り、ESC で閉じる
    useEffect(() => {
        if (!state) return;
        const onKey = (e: KeyboardEvent) => {
            if (e.key === 'ArrowLeft') prevPage();
            else if (e.key === 'ArrowRight') nextPage();
            else if (e.key === 'Escape') close();
        };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [state, prevPage, nextPage, close]);

    return { state, open, close, prevPage, nextPage, maxPage };
}
