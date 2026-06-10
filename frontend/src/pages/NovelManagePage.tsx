import { HammerIcon, Layers, Share2, Terminal, Wrench } from 'lucide-react';

import { formatSqliteUtcAsJst } from '../utils/date';

import {
    AmazonImportButton,
    BookSelectorPanel,
    FinishedJobCard,
    QueuedJobCard,
    RunningJobCard,
    SectionHeader,
} from '../components/novel_build';
import { OCRPanel } from '../features/ocr/OCRPanel';
import { useNovelManage } from '../hooks/useNovelManage';

const TAB_BASE =
    'flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors';
const TAB_ACTIVE = 'border-primary-500 text-primary-600 dark:text-primary-400';
const TAB_INACTIVE =
    'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 hover:border-gray-300 dark:hover:border-gray-600';

export default function NovelManagePage() {
    const {
        activeTab,
        handleTabChange,
        status,
        isEnqueuing,
        enqueueError,
        cancel,
        // Full Build
        allBooks,
        setAllBooks,
        selectedBook,
        setSelectedBook,
        showBuilt,
        handleShowBuiltChange,
        filteredBooks,
        handleEnqueueBuild,
        // コンテキスト生成
        allBooksCtx,
        setAllBooksCtx,
        selectedBookCtx,
        setSelectedBookCtx,
        showBuiltCtx,
        handleShowBuiltCtxChange,
        filteredBooksCtx,
        handleEnqueueCtx,
        // 関係グラフ生成
        allBooksRel,
        setAllBooksRel,
        selectedBookRel,
        setSelectedBookRel,
        handleEnqueueRelations,
        books,
        unifiedRows,
    } = useNovelManage();

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
                <AmazonImportButton />
            </div>

            {/* タブ */}
            <div className="border-b border-gray-200 dark:border-gray-700 mb-6">
                <div className="flex">
                    <button
                        onClick={() => handleTabChange('ocr')}
                        className={`${TAB_BASE} ${activeTab === 'ocr' ? TAB_ACTIVE : TAB_INACTIVE}`}
                    >
                        <Terminal className="w-4 h-4" />
                        OCR 管理
                    </button>
                    <button
                        onClick={() => handleTabChange('build')}
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
                    <BookSelectorPanel
                        title="Full Build を実行"
                        icon={<HammerIcon className="w-4 h-4" />}
                        allBooks={allBooks}
                        setAllBooks={setAllBooks}
                        showBuilt={showBuilt}
                        onShowBuiltChange={handleShowBuiltChange}
                        books={filteredBooks}
                        selectedBook={selectedBook}
                        setSelectedBook={setSelectedBook}
                        onEnqueue={handleEnqueueBuild}
                        isEnqueuing={isEnqueuing}
                        buttonLabel="Full Build"
                        buttonIcon={<HammerIcon className="w-4 h-4" />}
                        buttonVariant="primary"
                        className="mb-4"
                    />

                    <BookSelectorPanel
                        title="コンテキスト生成を実行"
                        icon={<Layers className="w-4 h-4" />}
                        allBooks={allBooksCtx}
                        setAllBooks={setAllBooksCtx}
                        showBuilt={showBuiltCtx}
                        onShowBuiltChange={handleShowBuiltCtxChange}
                        books={filteredBooksCtx}
                        selectedBook={selectedBookCtx}
                        setSelectedBook={setSelectedBookCtx}
                        onEnqueue={handleEnqueueCtx}
                        isEnqueuing={isEnqueuing}
                        buttonLabel="コンテキスト生成"
                        buttonIcon={<Layers className="w-4 h-4" />}
                        buttonVariant="secondary"
                        className="mb-4"
                    />

                    <BookSelectorPanel
                        title="関係グラフ生成を実行"
                        icon={<Share2 className="w-4 h-4" />}
                        allBooks={allBooksRel}
                        setAllBooks={setAllBooksRel}
                        books={books}
                        selectedBook={selectedBookRel}
                        setSelectedBook={setSelectedBookRel}
                        onEnqueue={handleEnqueueRelations}
                        isEnqueuing={isEnqueuing}
                        buttonLabel="関係グラフ生成"
                        buttonIcon={<Share2 className="w-4 h-4" />}
                        buttonVariant="indigo"
                        className="mb-8"
                    />

                    {enqueueError && (
                        <p className="text-sm text-red-500 dark:text-red-400 -mt-6 mb-6">
                            {enqueueError}
                        </p>
                    )}

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
                                        {formatSqliteUtcAsJst(row.time)}
                                    </span>
                                )}
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}
