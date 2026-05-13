/**
 * 4.6 本構築専用管理画面（/novel/build）。
 *
 * Full Build ジョブのエンキュー・キュー可視化・進捗表示。
 * 実行中セクション / 待機中セクション / 完了済みセクションの 3 分割リスト。
 */
import { useEffect, useState } from 'react';
import { HammerIcon, Loader2 } from 'lucide-react';

import {
    FinishedJobCard,
    QueuedJobCard,
    RunningJobCard,
    SectionHeader,
} from '../components/novel_build';
import { fetchBooks } from '../features/novel_db/api';
import type { BookSummary } from '../features/novel_db/types';
import { useNovelBuildQueue } from '../hooks/novel_build';

export default function NovelBuildPage() {
    const { status, isEnqueuing, enqueueError, enqueue, cancel } = useNovelBuildQueue();
    const [books, setBooks] = useState<BookSummary[]>([]);
    const [allBooks, setAllBooks] = useState(false);
    const [selectedBook, setSelectedBook] = useState('');

    useEffect(() => {
        fetchBooks()
            .then((data) => {
                setBooks(data);
                if (data.length > 0) setSelectedBook(data[0].name);
            })
            .catch(() => {});
    }, []);

    const handleEnqueue = () => {
        if (allBooks) {
            void enqueue(null, true);
        } else {
            if (!selectedBook) return;
            void enqueue(selectedBook, false);
        }
    };

    return (
        <div className="max-w-3xl mx-auto px-4 py-8">
            {/* ヘッダー */}
            <div className="flex items-center gap-3 mb-8">
                <div className="bg-primary-100 dark:bg-primary-900/40 p-2 rounded-lg">
                    <HammerIcon className="w-5 h-5 text-primary-600 dark:text-primary-400" />
                </div>
                <div>
                    <h1 className="text-xl font-bold text-gray-900 dark:text-gray-100">
                        本構築管理
                    </h1>
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                        OCR 済み書籍の Full Build（Embedding → サマリ → 登場人物 → コンテキスト）
                    </p>
                </div>
            </div>

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
                            <span className="text-gray-700 dark:text-gray-300">個別指定</span>
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
                        <select
                            value={selectedBook}
                            onChange={(e) => setSelectedBook(e.target.value)}
                            className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-primary-500"
                        >
                            {books.map((b) => (
                                <option key={b.name} value={b.name}>
                                    {b.name}
                                </option>
                            ))}
                            {books.length === 0 && (
                                <option value="">（書籍が見つかりません）</option>
                            )}
                        </select>
                    )}

                    {enqueueError && (
                        <p className="text-sm text-red-500 dark:text-red-400">{enqueueError}</p>
                    )}

                    <button
                        onClick={handleEnqueue}
                        disabled={isEnqueuing || (!allBooks && !selectedBook)}
                        className="flex items-center justify-center gap-2 px-4 py-2 bg-primary-600 hover:bg-primary-700 disabled:bg-gray-300 dark:disabled:bg-gray-700 text-white text-sm font-medium rounded-lg transition-colors"
                    >
                        {isEnqueuing ? (
                            <Loader2 className="w-4 h-4 animate-spin" />
                        ) : (
                            <HammerIcon className="w-4 h-4" />
                        )}
                        Full Build をエンキュー
                    </button>
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
        </div>
    );
}
