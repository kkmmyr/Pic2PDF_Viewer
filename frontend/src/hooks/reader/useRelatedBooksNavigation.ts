import { useState, useCallback } from 'react';
import type { RelatedBooks } from '@/hooks/reader/useRelatedBooks';

interface UseRelatedBooksNavigationProps {
    relatedBooks: RelatedBooks;
    onSelectPdf: ((name: string) => void) | undefined;
    recordView: (path: string, name: string) => void;
    currentPath: string;
}

interface UseRelatedBooksNavigationReturn {
    isOnRelatedPage: boolean;
    setIsOnRelatedPage: (v: boolean) => void;
    handleNextAtEnd: () => void;
    handlePrevIntercept: () => boolean;
    handleSelectRelated: (name: string) => void;
}

/**
 * 関連書籍ページへの遷移・選択ロジックをカプセル化する。
 *
 * - 末尾で次へ送ると関連書籍ページに切替（候補なしなら無視）
 * - 関連書籍ページで前へ送ると最終ページに戻る
 * - 関連書籍の選択時に recordView を呼んでから onSelectPdf を発火
 */
export function useRelatedBooksNavigation({
    relatedBooks,
    onSelectPdf,
    recordView,
    currentPath,
}: UseRelatedBooksNavigationProps): UseRelatedBooksNavigationReturn {
    const [isOnRelatedPage, setIsOnRelatedPage] = useState(false);

    const handleNextAtEnd = useCallback(() => {
        if (relatedBooks.series.length === 0 && relatedBooks.authors.length === 0) return;
        if (!onSelectPdf) return;
        setIsOnRelatedPage(true);
    }, [relatedBooks, onSelectPdf]);

    const handlePrevIntercept = useCallback(() => {
        if (!isOnRelatedPage) return false;
        setIsOnRelatedPage(false);
        return true;
    }, [isOnRelatedPage]);

    const handleSelectRelated = useCallback(
        (name: string) => {
            if (!onSelectPdf) return;
            recordView(currentPath, name);
            onSelectPdf(name);
        },
        [onSelectPdf, recordView, currentPath],
    );

    return {
        isOnRelatedPage,
        setIsOnRelatedPage,
        handleNextAtEnd,
        handlePrevIntercept,
        handleSelectRelated,
    };
}
