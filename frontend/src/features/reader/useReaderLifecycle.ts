import { useEffect, useRef } from 'react';

interface ReaderLifecycleProps {
    selectedPdf: string;
    initialPage?: number;
    isImageMode: boolean;
    imageNumPages: number;
    numPages: number;
    pageNumber: number;
    resetEditMode: () => void;
    resetNumPages: () => void;
    resetAutoSpread: () => void;
    handleCloseSearch: () => void;
    resetPage: () => void;
    setIsOnRelatedPage: (value: boolean) => void;
    setNumPages: (value: number) => void;
    setPageNumber: (value: number) => void;
}

/** 書籍切替時の副作用を順序を保って登録する。通信やURL操作は呼出し元が所有する。 */
export function useReaderLifecycle({
    selectedPdf,
    initialPage,
    isImageMode,
    imageNumPages,
    numPages,
    pageNumber,
    resetEditMode,
    resetNumPages,
    resetAutoSpread,
    handleCloseSearch,
    resetPage,
    setIsOnRelatedPage,
    setNumPages,
    setPageNumber,
}: ReaderLifecycleProps) {
    const initialPageKey = useRef<string | null>(null);

    useEffect(() => {
        resetEditMode();
        resetNumPages();
        resetAutoSpread();
        handleCloseSearch();
        resetPage();
        setIsOnRelatedPage(false);
    }, [
        selectedPdf,
        resetPage,
        handleCloseSearch,
        resetEditMode,
        resetAutoSpread,
        resetNumPages,
        setIsOnRelatedPage,
    ]);

    // 書籍 state のリセット後に画像ページ数を同期する。キャッシュ済みの画像一覧が
    // 初回 render から存在する再オープンでも、numPages=0 が後勝ちしない順序にする。
    useEffect(() => {
        if (isImageMode) setNumPages(imageNumPages);
    }, [selectedPdf, isImageMode, imageNumPages, setNumPages]);

    useEffect(() => {
        if (numPages <= 0) return;
        const key = `${selectedPdf}\u0000${initialPage ?? 1}`;
        if (initialPageKey.current === key) return;
        initialPageKey.current = key;
        setPageNumber(Math.min(initialPage ?? 1, numPages));
    }, [selectedPdf, initialPage, numPages, setPageNumber]);

    // ページペア切替時に Auto 見開き判定をリセット。直後に PageRenderer の onRenderSuccess
    // で左右両ページの寸法が通知され、片方でも横長なら 1 ページ表示に確定する。
    useEffect(() => {
        resetAutoSpread();
    }, [pageNumber, resetAutoSpread]);
}
