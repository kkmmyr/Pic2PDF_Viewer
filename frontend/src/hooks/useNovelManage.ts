import { useCallback, useEffect, useState } from 'react';

import { fetchBooks } from '../features/novel_db/api';
import type { BookSummary } from '../features/novel_db/types';
import type { BuildMode } from '../features/novel_build/types';
import { useNovelBuildQueue } from './novel_build';
import { useOcrStatus } from './useOcrStatus';

export type Tab = 'ocr' | 'build';

export interface UnifiedRow {
    key: string;
    type: string;
    target: string;
    state: string;
    stateClass: string;
    time?: string;
}

function modeLabel(mode?: BuildMode): string {
    return mode === 'generate_contexts' ? 'コンテキスト生成' : 'Full Build';
}

export interface UseNovelManage {
    activeTab: Tab;
    handleTabChange: (tab: Tab) => void;
    status: ReturnType<typeof useNovelBuildQueue>['status'];
    isEnqueuing: boolean;
    enqueueError: string | null;
    cancel: (jobId: number) => Promise<void>;
    ocrStatus: ReturnType<typeof useOcrStatus>['status'];
    books: BookSummary[];
    // Full Build 用
    allBooks: boolean;
    setAllBooks: (v: boolean) => void;
    selectedBook: string;
    setSelectedBook: (v: string) => void;
    showBuilt: boolean;
    handleShowBuiltChange: (v: boolean) => void;
    filteredBooks: BookSummary[];
    handleEnqueueBuild: () => void;
    // コンテキスト生成用
    allBooksCtx: boolean;
    setAllBooksCtx: (v: boolean) => void;
    selectedBookCtx: string;
    setSelectedBookCtx: (v: string) => void;
    showBuiltCtx: boolean;
    handleShowBuiltCtxChange: (v: boolean) => void;
    filteredBooksCtx: BookSummary[];
    handleEnqueueCtx: () => void;
    unifiedRows: UnifiedRow[];
}

export function useNovelManage(): UseNovelManage {
    const [activeTab, setActiveTab] = useState<Tab>('ocr');
    // OCR タブは初期タブなので初めから有効。Build タブは初訪問時に有効化する遅延起動パターン。
    const [buildEnabled, setBuildEnabled] = useState(false);
    const [ocrEnabled] = useState(true);

    const { status, isEnqueuing, enqueueError, enqueue, cancel } = useNovelBuildQueue(buildEnabled);
    const { status: ocrStatus } = useOcrStatus(ocrEnabled);

    const [books, setBooks] = useState<BookSummary[]>([]);
    // Full Build 用
    const [allBooks, setAllBooks] = useState(false);
    const [selectedBook, setSelectedBook] = useState('');
    const [showBuilt, setShowBuilt] = useState(false);
    // コンテキスト生成用
    const [allBooksCtx, setAllBooksCtx] = useState(false);
    const [selectedBookCtx, setSelectedBookCtx] = useState('');
    const [showBuiltCtx, setShowBuiltCtx] = useState(false);

    useEffect(() => {
        fetchBooks()
            .then((data) => {
                // ocr_done_at または indexed_at があれば Build 対象（pdf_text モードは ocr_done_at を立てない）
                const buildable = data.filter(
                    (b) => b.ocr_done_at !== null || b.indexed_at !== null,
                );
                setBooks(buildable);
                const unbuilt = buildable.filter((b) => b.indexed_at === null);
                const first = unbuilt.length > 0 ? unbuilt[0].name : '';
                setSelectedBook(first);
                setSelectedBookCtx(first);
            })
            .catch(() => {});
    }, []);

    const handleTabChange = useCallback((tab: Tab) => {
        setActiveTab(tab);
        if (tab === 'build') setBuildEnabled(true);
    }, []);

    const filteredBooks = books.filter((b) =>
        showBuilt ? b.indexed_at !== null : b.indexed_at === null,
    );

    const filteredBooksCtx = books.filter((b) =>
        showBuiltCtx ? b.indexed_at !== null : b.indexed_at === null,
    );

    const handleShowBuiltChange = useCallback(
        (value: boolean) => {
            const next = books.filter((b) =>
                value ? b.indexed_at !== null : b.indexed_at === null,
            );
            setShowBuilt(value);
            setSelectedBook(next.length > 0 ? next[0].name : '');
        },
        [books],
    );

    const handleShowBuiltCtxChange = useCallback(
        (value: boolean) => {
            const next = books.filter((b) =>
                value ? b.indexed_at !== null : b.indexed_at === null,
            );
            setShowBuiltCtx(value);
            setSelectedBookCtx(next.length > 0 ? next[0].name : '');
        },
        [books],
    );

    const handleEnqueueBuild = useCallback(() => {
        if (allBooks) {
            void enqueue(null, true, 'full_build');
        } else {
            if (!selectedBook) return;
            void enqueue(selectedBook, false, 'full_build');
        }
    }, [allBooks, selectedBook, enqueue]);

    const handleEnqueueCtx = useCallback(() => {
        if (allBooksCtx) {
            void enqueue(null, true, 'generate_contexts');
        } else {
            if (!selectedBookCtx) return;
            void enqueue(selectedBookCtx, false, 'generate_contexts');
        }
    }, [allBooksCtx, selectedBookCtx, enqueue]);

    // 全ジョブ履歴行を構築
    const unifiedRows: UnifiedRow[] = [];

    if (ocrStatus === 'running') {
        unifiedRows.push({
            key: 'ocr-running',
            type: 'OCR',
            target: '-',
            state: '実行中',
            stateClass:
                'bg-primary-100 text-primary-700 dark:bg-primary-900/40 dark:text-primary-300',
        });
    } else if (ocrStatus === 'error') {
        unifiedRows.push({
            key: 'ocr-error',
            type: 'OCR',
            target: '-',
            state: 'エラー',
            stateClass: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
        });
    }

    if (status.current_job) {
        const j = status.current_job;
        unifiedRows.push({
            key: `build-running-${j.id}`,
            type: modeLabel(j.mode),
            target: j.target_id ?? '全冊',
            state: '実行中',
            stateClass:
                'bg-primary-100 text-primary-700 dark:bg-primary-900/40 dark:text-primary-300',
            time: j.started_at,
        });
    }

    for (const j of status.queued_jobs) {
        unifiedRows.push({
            key: `build-queued-${j.id}`,
            type: modeLabel(j.mode),
            target: j.target_id ?? '全冊',
            state: '待機中',
            stateClass: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300',
            time: j.enqueued_at,
        });
    }

    for (const j of status.recent_finished) {
        const stateLabel =
            { completed: '完了', failed: '失敗', canceled: 'キャンセル' }[j.state] ?? '完了';
        const stateClass =
            {
                completed: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300',
                failed: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
                canceled: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300',
            }[j.state] ?? 'bg-gray-100 text-gray-600';
        unifiedRows.push({
            key: `build-finished-${j.id}`,
            type: modeLabel(j.mode),
            target: j.target_id ?? '全冊',
            state: stateLabel,
            stateClass,
            time: j.finished_at,
        });
    }

    return {
        activeTab,
        handleTabChange,
        status,
        isEnqueuing,
        enqueueError,
        cancel,
        ocrStatus,
        books,
        allBooks,
        setAllBooks,
        selectedBook,
        setSelectedBook,
        showBuilt,
        handleShowBuiltChange,
        filteredBooks,
        handleEnqueueBuild,
        allBooksCtx,
        setAllBooksCtx,
        selectedBookCtx,
        setSelectedBookCtx,
        showBuiltCtx,
        handleShowBuiltCtxChange,
        filteredBooksCtx,
        handleEnqueueCtx,
        unifiedRows,
    };
}
