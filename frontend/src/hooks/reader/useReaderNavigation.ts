import { useState, useEffect, useCallback } from 'react';
import { nextReaderPage, previousReaderPage } from '@/features/reader/page-navigation';
import type { ReadingDirection } from '@/types';

interface UseReaderNavigationProps {
    numPages: number;
    isSpread: boolean;
    direction: ReadingDirection;
    isActive: boolean;
    /**
     * 末尾で next が呼ばれたときの追加処理（例: 関連書籍ページへ遷移）。
     * 既にページが進められない状況のみ呼ばれる。
     */
    onNextAtEnd?: () => void;
    /**
     * prev が呼ばれたときの先行フック。true を返すと内部のページ戻し処理を抑止する
     * （例: 関連書籍ページから最終ページに戻る場合）。
     */
    onPrevIntercept?: () => boolean;
}

interface UseReaderNavigationReturn {
    pageNumber: number;
    setPageNumber: (page: number) => void;
    handleNext: (e?: React.MouseEvent | KeyboardEvent) => void;
    handlePrev: (e?: React.MouseEvent | KeyboardEvent) => void;
    resetPage: () => void;
}

/**
 * リーダーのページナビゲーションを管理するカスタムフック
 */
export function useReaderNavigation({
    numPages,
    isSpread,
    direction,
    isActive,
    onNextAtEnd,
    onPrevIntercept,
}: UseReaderNavigationProps): UseReaderNavigationReturn {
    const [pageNumber, setPageNumber] = useState(1);

    const handleNext = useCallback(
        (e?: React.MouseEvent | KeyboardEvent) => {
            e?.stopPropagation?.();

            const nextPage = nextReaderPage({
                page: pageNumber,
                numPages,
                isSpread,
                direction,
            });
            if (nextPage === null) onNextAtEnd?.();
            else setPageNumber(nextPage);
        },
        [pageNumber, numPages, isSpread, direction, onNextAtEnd],
    );

    const handlePrev = useCallback(
        (e?: React.MouseEvent | KeyboardEvent) => {
            e?.stopPropagation?.();

            if (onPrevIntercept?.()) return;

            const previousPage = previousReaderPage({
                page: pageNumber,
                numPages,
                isSpread,
                direction,
            });
            if (previousPage !== null) setPageNumber(previousPage);
        },
        [pageNumber, numPages, isSpread, direction, onPrevIntercept],
    );

    const resetPage = useCallback(() => {
        setPageNumber(1);
    }, []);

    // Keyboard Navigation
    useEffect(() => {
        if (!isActive) return;

        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === 'ArrowLeft') {
                if (direction === 'rtl') handleNext();
                else handlePrev();
            } else if (e.key === 'ArrowRight') {
                if (direction === 'rtl') handlePrev();
                else handleNext();
            }
        };

        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [isActive, direction, handleNext, handlePrev]);

    return {
        pageNumber,
        setPageNumber,
        handleNext,
        handlePrev,
        resetPage,
    };
}
