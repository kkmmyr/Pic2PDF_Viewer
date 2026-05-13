import { useEffect, useState } from 'react';
import { Download, HammerIcon, Layers, Loader2, Terminal, Wrench } from 'lucide-react';

import { API_ENDPOINTS } from '../config/api';
import apiClient from '../config/api_client';
import { useToast } from '../hooks';
import { ToastContainer } from '../components/reader/ToastContainer';

import {
    FinishedJobCard,
    QueuedJobCard,
    RunningJobCard,
    SectionHeader,
} from '../components/novel_build';
import { OCRPanel } from '../features/ocr/OCRPanel';
import { fetchBooks } from '../features/novel_db/api';
import type { BookSummary } from '../features/novel_db/types';
import type { BuildMode } from '../features/novel_build/types';
import { useNovelBuildQueue } from '../hooks/novel_build';
import { useOcrStatus } from '../hooks/useOcrStatus';

type Tab = 'ocr' | 'build';

interface UnifiedRow {
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

export default function NovelManagePage() {
    const [activeTab, setActiveTab] = useState<Tab>('ocr');
    const { status, isEnqueuing, enqueueError, enqueue, cancel } = useNovelBuildQueue();
    const { status: ocrStatus } = useOcrStatus();
    const [books, setBooks] = useState<BookSummary[]>([]);
    const [allBooks, setAllBooks] = useState(false);
    const [selectedBook, setSelectedBook] = useState('');
    const [showBuilt, setShowBuilt] = useState(false);
    const [isImporting, setIsImporting] = useState(false);
    const { toasts, showToast, dismissToast } = useToast();

    useEffect(() => {
        fetchBooks()
            .then((data) => {
                // ocr_done_at または indexed_at があれば Build 対象（pdf_text モードは ocr_done_at を立てない）
                const buildable = data.filter(
                    (b) => b.ocr_done_at !== null || b.indexed_at !== null,
                );
                setBooks(buildable);
                const unbuilt = buildable.filter((b) => b.indexed_at === null);
                setSelectedBook(unbuilt.length > 0 ? unbuilt[0].name : '');
            })
            .catch(() => {});
    }, []);

    const filteredBooks = books.filter((b) =>
        showBuilt ? b.indexed_at !== null : b.indexed_at === null,
    );

    const handleShowBuiltChange = (value: boolean) => {
        const next = books.filter((b) => (value ? b.indexed_at !== null : b.indexed_at === null));
        setShowBuilt(value);
        setSelectedBook(next.length > 0 ? next[0].name : '');
    };

    const handleAmazonImport = async () => {
        setIsImporting(true);
        try {
            const [novelRes, comicRes] = await Promise.allSettled([
                apiClient.post<{ updated: number; skipped: number; unmatched: number }>(
                    API_ENDPOINTS.AMAZON_IMPORT('novel'),
                ),
                apiClient.post<{ updated: number; skipped: number; unmatched: number }>(
                    API_ENDPOINTS.AMAZON_IMPORT('comic'),
                ),
            ]);

            const novelData =
                novelRes.status === 'fulfilled' ? novelRes.value.data : null;
            const comicData =
                comicRes.status === 'fulfilled' ? comicRes.value.data : null;

            const updated = (novelData?.updated ?? 0) + (comicData?.updated ?? 0);
            const skipped = (novelData?.skipped ?? 0) + (comicData?.skipped ?? 0);
            const unmatched = (novelData?.unmatched ?? 0) + (comicData?.unmatched ?? 0);

            const hasError =
                novelRes.status === 'rejected' || comicRes.status === 'rejected';

            if (hasError && updated === 0) {
                const msg =
                    novelRes.status === 'rejected'
                        ? (novelRes.reason as Error).message
                        : (comicRes.reason as Error).message;
                showToast(`インポート失敗: ${msg}`, 'error');
            } else {
                showToast(
                    `更新: ${updated} 件 / スキップ: ${skipped} 件 / 未マッチ: ${unmatched} 件`,
                    'success',
                );
            }
        } finally {
            setIsImporting(false);
        }
    };

    const handleEnqueue = (mode: 'full_build' | 'generate_contexts' = 'full_build') => {
        if (allBooks) {
            void enqueue(null, true, mode);
        } else {
            if (!selectedBook) return;
            void enqueue(selectedBook, false, mode);
        }
    };

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

    const TAB_BASE =
        'flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors';
    const TAB_ACTIVE = 'border-primary-500 text-primary-600 dark:text-primary-400';
    const TAB_INACTIVE =
        'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 hover:border-gray-300 dark:hover:border-gray-600';

    return (
        <div className="max-w-3xl mx-auto px-4 py-8">
            {/* ヘッダー */}
            <div className="flex items-center gap-3 mb-6">
                <div className="bg-primary-100 dark:bg-primary-900/40 p-2 rounded-lg">
                    <Wrench className="w-5 h-5 text-primary-600 dark:text-primary-400" />
                </div>
                <div className="flex-1">
                    <h1 className="text-xl font-bold text-gray-900 dark:text-gray-100">構築管理</h1>
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                        OCR → Full Build の順で実施する統合管理画面
                    </p>
                </div>
                <button
                    onClick={() => void handleAmazonImport()}
                    disabled={isImporting}
                    className="flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50 transition-colors"
                    title="Amazon CSV から著者・ASIN を補完（novel + comic）"
                >
                    {isImporting ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                        <Download className="w-4 h-4" />
                    )}
                    Amazon CSV
                </button>
            </div>

            {/* タブ */}
            <div className="border-b border-gray-200 dark:border-gray-700 mb-6">
                <div className="flex">
                    <button
                        onClick={() => setActiveTab('ocr')}
                        className={`${TAB_BASE} ${activeTab === 'ocr' ? TAB_ACTIVE : TAB_INACTIVE}`}
                    >
                        <Terminal className="w-4 h-4" />
                        OCR 管理
                    </button>
                    <button
                        onClick={() => setActiveTab('build')}
                        className={`${TAB_BASE} ${activeTab === 'build' ? TAB_ACTIVE : TAB_INACTIVE}`}
                    >
                        <HammerIcon className="w-4 h-4" />
                        Full Build 管理
                    </button>
                </div>
            </div>

            {/* OCR タブ */}
            {activeTab === 'ocr' && (
                <div className="h-[500px] flex flex-col">
                    <OCRPanel />
                </div>
            )}

            {/* Full Build タブ */}
            {activeTab === 'build' && (
                <>
                    {/* エンキューフォーム */}
                    <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl p-5 mb-8">
                        <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-4">
                            Full Build を実行
                        </h2>
                        <div className="flex flex-col gap-3">
                            <div className="flex gap-4 text-sm">
                                <label className="flex items-center gap-2 cursor-pointer">
                                    <input
                                        type="radio"
                                        checked={!allBooks}
                                        onChange={() => setAllBooks(false)}
                                        className="text-primary-500"
                                    />
                                    <span className="text-gray-700 dark:text-gray-300">
                                        個別指定
                                    </span>
                                </label>
                                <label className="flex items-center gap-2 cursor-pointer">
                                    <input
                                        type="radio"
                                        checked={allBooks}
                                        onChange={() => setAllBooks(true)}
                                        className="text-primary-500"
                                    />
                                    <span className="text-gray-700 dark:text-gray-300">全冊</span>
                                </label>
                            </div>

                            {!allBooks && (
                                <>
                                    <div className="flex gap-4 text-sm ml-1">
                                        <label className="flex items-center gap-1.5 cursor-pointer">
                                            <input
                                                type="radio"
                                                checked={!showBuilt}
                                                onChange={() => handleShowBuiltChange(false)}
                                                className="text-primary-500"
                                            />
                                            <span className="text-gray-600 dark:text-gray-400">
                                                未完了
                                            </span>
                                        </label>
                                        <label className="flex items-center gap-1.5 cursor-pointer">
                                            <input
                                                type="radio"
                                                checked={showBuilt}
                                                onChange={() => handleShowBuiltChange(true)}
                                                className="text-primary-500"
                                            />
                                            <span className="text-gray-600 dark:text-gray-400">
                                                完了済み
                                            </span>
                                        </label>
                                    </div>
                                    <select
                                        value={selectedBook}
                                        onChange={(e) => setSelectedBook(e.target.value)}
                                        className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-primary-500"
                                    >
                                        {filteredBooks.map((b) => (
                                            <option key={b.name} value={b.name}>
                                                {b.name}
                                            </option>
                                        ))}
                                        {filteredBooks.length === 0 && (
                                            <option value="">（書籍が見つかりません）</option>
                                        )}
                                    </select>
                                </>
                            )}

                            {enqueueError && (
                                <p className="text-sm text-red-500 dark:text-red-400">
                                    {enqueueError}
                                </p>
                            )}

                            <div className="flex gap-2">
                                <button
                                    onClick={() => handleEnqueue('full_build')}
                                    disabled={isEnqueuing || (!allBooks && !selectedBook)}
                                    className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-primary-600 hover:bg-primary-700 disabled:bg-gray-300 dark:disabled:bg-gray-700 text-white text-sm font-medium rounded-lg transition-colors"
                                >
                                    {isEnqueuing ? (
                                        <Loader2 className="w-4 h-4 animate-spin" />
                                    ) : (
                                        <HammerIcon className="w-4 h-4" />
                                    )}
                                    Full Build
                                </button>
                                <button
                                    onClick={() => handleEnqueue('generate_contexts')}
                                    disabled={isEnqueuing || (!allBooks && !selectedBook)}
                                    className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-gray-600 hover:bg-gray-700 disabled:bg-gray-300 dark:disabled:bg-gray-700 text-white text-sm font-medium rounded-lg transition-colors"
                                >
                                    {isEnqueuing ? (
                                        <Loader2 className="w-4 h-4 animate-spin" />
                                    ) : (
                                        <Layers className="w-4 h-4" />
                                    )}
                                    コンテキスト生成
                                </button>
                            </div>
                        </div>
                    </div>

                    {/* 実行中 */}
                    <section className="mb-6">
                        <SectionHeader title="実行中" />
                        {status.current_job ? (
                            <RunningJobCard job={status.current_job} />
                        ) : (
                            <p className="text-sm text-gray-400 dark:text-gray-500 py-2">
                                実行中のジョブはありません
                            </p>
                        )}
                    </section>

                    {/* 待機中 */}
                    <section className="mb-6">
                        <SectionHeader title="待機中" count={status.queued_jobs.length} />
                        {status.queued_jobs.length > 0 ? (
                            <div className="flex flex-col gap-2">
                                {status.queued_jobs.map((job) => (
                                    <QueuedJobCard key={job.id} job={job} onCancel={cancel} />
                                ))}
                            </div>
                        ) : (
                            <p className="text-sm text-gray-400 dark:text-gray-500 py-2">
                                待機中のジョブはありません
                            </p>
                        )}
                    </section>

                    {/* 完了済み */}
                    <section>
                        <SectionHeader title="完了済み" count={status.recent_finished.length} />
                        {status.recent_finished.length > 0 ? (
                            <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl px-4 py-2">
                                {status.recent_finished.map((job) => (
                                    <FinishedJobCard key={job.id} job={job} />
                                ))}
                            </div>
                        ) : (
                            <p className="text-sm text-gray-400 dark:text-gray-500 py-2">
                                完了済みのジョブはありません
                            </p>
                        )}
                    </section>
                </>
            )}

            {/* 全ジョブ履歴（常時表示の共通セクション） */}
            <div className="mt-10 pt-6 border-t border-gray-200 dark:border-gray-700">
                <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">
                    全ジョブ履歴
                </h2>
                {unifiedRows.length === 0 ? (
                    <p className="text-sm text-gray-400 dark:text-gray-500">ジョブはありません</p>
                ) : (
                    <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl divide-y divide-gray-100 dark:divide-gray-700">
                        {unifiedRows.map((row) => (
                            <div
                                key={row.key}
                                className="flex items-center gap-3 px-4 py-3 text-sm"
                            >
                                <span className="w-28 font-medium text-gray-700 dark:text-gray-300 shrink-0 truncate">
                                    {row.type}
                                </span>
                                <span className="flex-1 text-gray-600 dark:text-gray-400 truncate">
                                    {row.target}
                                </span>
                                <span
                                    className={`px-2 py-0.5 rounded-full text-xs font-medium shrink-0 ${row.stateClass}`}
                                >
                                    {row.state}
                                </span>
                                {row.time && (
                                    <span className="text-xs text-gray-400 dark:text-gray-500 shrink-0">
                                        {new Date(row.time).toLocaleString('ja-JP', {
                                            month: 'numeric',
                                            day: 'numeric',
                                            hour: '2-digit',
                                            minute: '2-digit',
                                        })}
                                    </span>
                                )}
                            </div>
                        ))}
                    </div>
                )}
            </div>
            <ToastContainer toasts={toasts} onDismiss={dismissToast} />
        </div>
    );
}
