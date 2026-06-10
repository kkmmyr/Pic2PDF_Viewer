import { useState, useEffect, useCallback } from 'react';
import type { ReadingDirection } from '../../types';

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

            if (!isSpread) {
                // Single Page Mode
                if (pageNumber < numPages) setPageNumber((prev) => prev + 1);
                else onNextAtEnd?.();
                return;
            }

            // Spread Mode
            if (direction === 'rtl') {
                // RTL:
                // Page 1 (Cover) -> Next -> Page 2 (Right) + Page 3 (Left) [Display: 3 | 2]
                if (pageNumber === 1) {
                    if (pageNumber + 1 <= numPages) setPageNumber(2);
                    else onNextAtEnd?.();
                } else {
                    if (pageNumber + 2 <= numPages) setPageNumber((prev) => prev + 2);
                    else onNextAtEnd?.();
                }
            } else {
                // LTR:
                // Page 1 (Left) + Page 2 (Right) -> Next -> Page 3 (Left) + Page 4 (Right)
                if (pageNumber + 2 <= numPages) setPageNumber((prev) => prev + 2);
                else if (pageNumber + 1 <= numPages) setPageNumber((prev) => prev + 1);
                else onNextAtEnd?.();
            }
        },
        [pageNumber, numPages, isSpread, direction, onNextAtEnd],
    );

    const handlePrev = useCallback(
        (e?: React.MouseEvent | KeyboardEvent) => {
            e?.stopPropagation?.();

            if (onPrevIntercept?.()) return;

            if (!isSpread) {
                // Single Page Mode
                if (pageNumber > 1) setPageNumber((prev) => prev - 1);
                return;
            }

            // Spread Mode
            if (direction === 'rtl') {
                // RTL:
                if (pageNumber === 2) {
                    setPageNumber(1);
                } else if (pageNumber > 2) {
                    setPageNumber((prev) => prev - 2);
                }
            } else {
                // LTR:
                if (pageNumber > 2) setPageNumber((prev) => prev - 2);
                else if (pageNumber === 2) setPageNumber(1);
            }
        },
        [pageNumber, isSpread, direction, onPrevIntercept],
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
