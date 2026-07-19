import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';

import { novelBooksQueryOptions } from '@/features/novel_db/queries';
import type { BookSummary } from '@/features/novel_db/types';
import { useBuildTarget } from '@/hooks/useBuildTarget';
import { buildUnifiedRows, type UnifiedRow } from '@/hooks/novel_build/buildUnifiedRows';
import { useNovelBuildQueue } from '@/hooks/novel_build/useNovelBuildQueue';
import { useOcrStatus } from '@/hooks/useOcrStatus';

export type Tab = 'ocr' | 'build';
export type { UnifiedRow } from '@/hooks/novel_build/buildUnifiedRows';

export interface UseNovelManage {
    activeTab: Tab;
    handleTabChange: (tab: Tab) => void;
    status: ReturnType<typeof useNovelBuildQueue>['status'];
    isEnqueuing: boolean;
    enqueueError: string | null;
    cancel: (jobId: number) => Promise<void>;
    ocrStatus: ReturnType<typeof useOcrStatus>['status'];
    books: BookSummary[];
    allBooks: boolean;
    setAllBooks: (v: boolean) => void;
    selectedBook: string;
    setSelectedBook: (v: string) => void;
    showBuilt: boolean;
    handleShowBuiltChange: (v: boolean) => void;
    filteredBooks: BookSummary[];
    handleEnqueueBuild: () => void;
    allBooksCtx: boolean;
    setAllBooksCtx: (v: boolean) => void;
    selectedBookCtx: string;
    setSelectedBookCtx: (v: string) => void;
    showBuiltCtx: boolean;
    handleShowBuiltCtxChange: (v: boolean) => void;
    filteredBooksCtx: BookSummary[];
    handleEnqueueCtx: () => void;
    allBooksRel: boolean;
    setAllBooksRel: (v: boolean) => void;
    selectedBookRel: string;
    setSelectedBookRel: (v: string) => void;
    handleEnqueueRelations: () => void;
    unifiedRows: UnifiedRow[];
}

export function useNovelManage(): UseNovelManage {
    const [activeTab, setActiveTab] = useState<Tab>('ocr');
    const [buildEnabled, setBuildEnabled] = useState(false);
    const { status, isEnqueuing, enqueueError, enqueue, cancel } = useNovelBuildQueue(buildEnabled);
    const { status: ocrStatus } = useOcrStatus(true);
    const booksQuery = useQuery({
        ...novelBooksQueryOptions(),
        select: (data) =>
            data.filter((book) => book.ocr_done_at !== null || book.indexed_at !== null),
    });
    const books = useMemo(() => booksQuery.data ?? [], [booksQuery.data]);
    const refetchBooks = booksQuery.refetch;

    const buildTarget = useBuildTarget('full_build', books, enqueue);
    const ctxTarget = useBuildTarget('generate_contexts', books, enqueue);
    const relTarget = useBuildTarget('generate_relations', books, enqueue);
    const setBuildSelected = buildTarget.setSelected;
    const setCtxSelected = ctxTarget.setSelected;
    const setRelSelected = relTarget.setSelected;
    const initializedRef = useRef(false);

    useEffect(() => {
        if (initializedRef.current || !booksQuery.isSuccess) return;
        const firstUnbuilt = books.find((book) => book.indexed_at === null)?.name ?? '';
        setBuildSelected(firstUnbuilt);
        setCtxSelected(firstUnbuilt);
        setRelSelected(books[0]?.name ?? '');
        initializedRef.current = true;
    }, [books, booksQuery.isSuccess, setBuildSelected, setCtxSelected, setRelSelected]);

    const previousRunningRef = useRef(false);
    useEffect(() => {
        if (previousRunningRef.current && !status.is_running) {
            void refetchBooks();
        }
        previousRunningRef.current = status.is_running;
    }, [refetchBooks, status.is_running]);

    const handleTabChange = useCallback((tab: Tab) => {
        setActiveTab(tab);
        if (tab === 'build') setBuildEnabled(true);
    }, []);

    return {
        activeTab,
        handleTabChange,
        status,
        isEnqueuing,
        enqueueError,
        cancel,
        ocrStatus,
        books,
        allBooks: buildTarget.all,
        setAllBooks: buildTarget.setAll,
        selectedBook: buildTarget.selected,
        setSelectedBook: buildTarget.setSelected,
        showBuilt: buildTarget.showBuilt,
        handleShowBuiltChange: buildTarget.handleShowBuiltChange,
        filteredBooks: buildTarget.filtered,
        handleEnqueueBuild: buildTarget.handleEnqueue,
        allBooksCtx: ctxTarget.all,
        setAllBooksCtx: ctxTarget.setAll,
        selectedBookCtx: ctxTarget.selected,
        setSelectedBookCtx: ctxTarget.setSelected,
        showBuiltCtx: ctxTarget.showBuilt,
        handleShowBuiltCtxChange: ctxTarget.handleShowBuiltChange,
        filteredBooksCtx: ctxTarget.filtered,
        handleEnqueueCtx: ctxTarget.handleEnqueue,
        allBooksRel: relTarget.all,
        setAllBooksRel: relTarget.setAll,
        selectedBookRel: relTarget.selected,
        setSelectedBookRel: relTarget.setSelected,
        handleEnqueueRelations: relTarget.handleEnqueue,
        unifiedRows: buildUnifiedRows(ocrStatus, status),
    };
}
