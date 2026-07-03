import { useCallback, useEffect, useRef, useState } from 'react';

import { fetchBooks } from '@/features/novel_db/api';
import type { BookSummary } from '@/features/novel_db/types';
import type { BuildMode } from '@/features/novel_build/types';
import { useNovelBuildQueue } from './novel_build';
import { useOcrStatus } from './useOcrStatus';
import { useBuildTarget } from './useBuildTarget';

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
    if (mode === 'generate_contexts') return 'コンテキスト生成';
    if (mode === 'generate_relations') return '関係グラフ生成';
    return 'Full Build';
}

function buildUnifiedRows(
    ocrStatus: ReturnType<typeof useOcrStatus>['status'],
    status: ReturnType<typeof useNovelBuildQueue>['status'],
): UnifiedRow[] {
    const rows: UnifiedRow[] = [];

    if (ocrStatus === 'running') {
        rows.push({
            key: 'ocr-running',
            type: 'OCR',
            target: '-',
            state: '実行中',
            stateClass:
                'bg-primary-100 text-primary-700 dark:bg-primary-900/40 dark:text-primary-300',
        });
    } else if (ocrStatus === 'error') {
        rows.push({
            key: 'ocr-error',
            type: 'OCR',
            target: '-',
            state: 'エラー',
            stateClass: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
        });
    }

    if (status.current_job) {
        const j = status.current_job;
        rows.push({
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
        rows.push({
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
        rows.push({
            key: `build-finished-${j.id}`,
            type: modeLabel(j.mode),
            target: j.target_id ?? '全冊',
            state: stateLabel,
            stateClass,
            time: j.finished_at,
        });
    }

    return rows;
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
    // 関係グラフ生成用
    allBooksRel: boolean;
    setAllBooksRel: (v: boolean) => void;
    selectedBookRel: string;
    setSelectedBookRel: (v: string) => void;
    handleEnqueueRelations: () => void;
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

    const buildTarget = useBuildTarget('full_build', books, enqueue);
    const ctxTarget = useBuildTarget('generate_contexts', books, enqueue);
    const relTarget = useBuildTarget('generate_relations', books, enqueue);

    // 各 setSelected は useState setter のため安定した参照
    const { setSelected: setBuildSelected } = buildTarget;
    const { setSelected: setCtxSelected } = ctxTarget;
    const { setSelected: setRelSelected } = relTarget;

    const refreshBooks = useCallback(
        (initSelect = false) => {
            fetchBooks()
                .then((data) => {
                    // ocr_done_at または indexed_at があれば Build 対象
                    const buildable = data.filter(
                        (b) => b.ocr_done_at !== null || b.indexed_at !== null,
                    );
                    setBooks(buildable);
                    if (initSelect) {
                        const unbuilt = buildable.filter((b) => b.indexed_at === null);
                        const first = unbuilt.length > 0 ? unbuilt[0].name : '';
                        setBuildSelected(first);
                        setCtxSelected(first);
                        setRelSelected(buildable.length > 0 ? buildable[0].name : '');
                    }
                })
                .catch(() => {});
        },
        [setBuildSelected, setCtxSelected, setRelSelected],
    );

    useEffect(() => {
        refreshBooks(true);
        // eslint-disable-next-line react-hooks/exhaustive-deps -- refreshBooks は setState セッターのみに依存し参照が安定するため、マウント時に一度だけ実行
    }, []);

    // ジョブ完了時（running → 非 running）に書籍一覧を再取得
    const prevIsRunningRef = useRef(false);
    useEffect(() => {
        if (prevIsRunningRef.current && !status.is_running) {
            refreshBooks();
        }
        prevIsRunningRef.current = status.is_running;
    }, [status.is_running, refreshBooks]);

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
        // Full Build（buildTarget から展開してインターフェースを維持）
        allBooks: buildTarget.all,
        setAllBooks: buildTarget.setAll,
        selectedBook: buildTarget.selected,
        setSelectedBook: buildTarget.setSelected,
        showBuilt: buildTarget.showBuilt,
        handleShowBuiltChange: buildTarget.handleShowBuiltChange,
        filteredBooks: buildTarget.filtered,
        handleEnqueueBuild: buildTarget.handleEnqueue,
        // コンテキスト生成
        allBooksCtx: ctxTarget.all,
        setAllBooksCtx: ctxTarget.setAll,
        selectedBookCtx: ctxTarget.selected,
        setSelectedBookCtx: ctxTarget.setSelected,
        showBuiltCtx: ctxTarget.showBuilt,
        handleShowBuiltCtxChange: ctxTarget.handleShowBuiltChange,
        filteredBooksCtx: ctxTarget.filtered,
        handleEnqueueCtx: ctxTarget.handleEnqueue,
        // 関係グラフ生成
        allBooksRel: relTarget.all,
        setAllBooksRel: relTarget.setAll,
        selectedBookRel: relTarget.selected,
        setSelectedBookRel: relTarget.setSelected,
        handleEnqueueRelations: relTarget.handleEnqueue,
        unifiedRows: buildUnifiedRows(ocrStatus, status),
    };
}
