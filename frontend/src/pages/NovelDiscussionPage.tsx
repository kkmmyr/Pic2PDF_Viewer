/**
 * B-28 読書会 番組台本生成ページ（/novel/discussion）。
 *
 * ホストキャラはレイ＆ミオ固定（サーバー側管理）のため、設定は書籍選択のみ。
 * ロジックは useDiscussion フックに委譲し、このページは JSX の
 * オーケストレーターのみとなっている。
 */
import { Loader2, RadioTower, RefreshCw, Square } from 'lucide-react';

import DiscussionHistoryItemCard from '@/components/novel_db/DiscussionHistoryItem';
import ScriptView, { ChecksBadge, ScriptExportButtons } from '@/components/novel_db/script-view';
import { useDiscussion } from '@/hooks/novel_db/useDiscussion';
import { useNovelDbBooks } from '@/hooks/novel_db';

const STAGE_LABELS = {
    planning: '構成を考え中…（数分かかります）',
    scripting: '台本を執筆中…',
} as const;

export default function NovelDiscussionPage() {
    const { books } = useNovelDbBooks();
    const {
        selectedBook,
        setSelectedBook,
        turns,
        segments,
        stage,
        checks,
        isGenerating,
        error,
        canGenerate,
        history,
        historyLoading,
        handleGenerate,
        handleRegenerate,
        handleCancel,
        handleDelete,
        bottomRef,
    } = useDiscussion();

    const failedChecks = checks?.results.filter((r) => !r.passed) ?? [];

    return (
        <div className="max-w-3xl mx-auto px-4 sm:px-6 py-6 space-y-6">
            {/* ヘッダー */}
            <div className="flex items-center gap-2">
                <RadioTower className="w-5 h-5 text-indigo-500" />
                <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100">
                    読書会 番組台本
                </h1>
                <span className="text-xs text-gray-400 dark:text-gray-500">
                    ホスト: レイ ＆ ミオ
                </span>
            </div>

            {/* 設定パネル */}
            <div className="space-y-4 border border-gray-200 dark:border-gray-700 rounded-xl p-4">
                {/* 書籍選択 */}
                <div>
                    <label
                        htmlFor="discussion-book-select"
                        className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
                    >
                        書籍を選択
                    </label>
                    <select
                        id="discussion-book-select"
                        value={selectedBook}
                        onChange={(e) => setSelectedBook(e.target.value)}
                        disabled={isGenerating}
                        className="w-full text-sm border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 disabled:opacity-50"
                    >
                        <option value="">— 書籍を選んでください —</option>
                        {books.map((b) => (
                            <option key={b.name} value={b.name}>
                                {b.name}
                                {b.series_id
                                    ? ` [${b.series_id}${b.volume != null ? ` ${b.volume}巻` : ''}]`
                                    : ''}
                            </option>
                        ))}
                    </select>
                </div>

                {/* 生成 / キャンセルボタン */}
                <div className="flex gap-2">
                    <button
                        type="button"
                        onClick={handleGenerate}
                        disabled={!canGenerate}
                        className="flex-1 py-2 text-sm font-medium rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-2 transition-colors"
                    >
                        {isGenerating ? (
                            <>
                                <Loader2 className="w-4 h-4 animate-spin" />
                                生成中...
                            </>
                        ) : (
                            <>
                                <RadioTower className="w-4 h-4" />
                                台本を生成
                            </>
                        )}
                    </button>
                    {isGenerating && (
                        <button
                            type="button"
                            onClick={handleCancel}
                            className="px-4 py-2 text-sm font-medium rounded-lg border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 flex items-center gap-1.5 transition-colors"
                        >
                            <Square className="w-3.5 h-3.5" />
                            中止
                        </button>
                    )}
                </div>

                {/* 進行段階表示 */}
                {isGenerating && stage && (
                    <div className="flex items-center gap-2 text-sm text-indigo-600 dark:text-indigo-400">
                        <Loader2 className="w-4 h-4 animate-spin" />
                        {STAGE_LABELS[stage]}
                    </div>
                )}
            </div>

            {/* エラー表示 */}
            {error && (
                <div className="rounded-lg bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 px-4 py-3 text-sm text-red-700 dark:text-red-300">
                    {error}
                </div>
            )}

            {/* 現在の生成結果 */}
            {turns.length > 0 && (
                <section className="space-y-3">
                    <div className="flex items-center gap-2 flex-wrap">
                        <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300">
                            生成結果
                        </h2>
                        {isGenerating && (
                            <span className="text-xs text-gray-400 font-normal">生成中...</span>
                        )}
                        {!isGenerating && checks && <ChecksBadge checks={checks} />}
                    </div>

                    <ScriptView turns={turns} segments={segments} />
                    <div ref={bottomRef} />

                    {/* 完了後: チェック不合格の内訳 + 再生成 + エクスポート */}
                    {!isGenerating && checks && failedChecks.length > 0 && (
                        <div className="rounded-lg bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 px-4 py-3 space-y-1">
                            <p className="text-sm font-medium text-amber-800 dark:text-amber-200">
                                機械チェックで不合格の項目があります
                            </p>
                            <ul className="text-xs text-amber-700 dark:text-amber-300 list-disc list-inside space-y-0.5">
                                {failedChecks.map((r) => (
                                    <li key={r.id}>{`${r.label} — ${r.detail}`}</li>
                                ))}
                            </ul>
                        </div>
                    )}
                    {!isGenerating && (
                        <div className="flex items-center gap-2 flex-wrap">
                            {checks && (
                                <button
                                    type="button"
                                    onClick={handleRegenerate}
                                    className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white transition-colors"
                                >
                                    <RefreshCw className="w-3.5 h-3.5" />
                                    再生成
                                </button>
                            )}
                            <ScriptExportButtons
                                bookName={selectedBook}
                                turns={turns}
                                segments={segments}
                            />
                        </div>
                    )}
                </section>
            )}

            {/* 履歴セクション */}
            {selectedBook && (
                <section className="space-y-3">
                    <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300">
                        過去の生成履歴
                        {historyLoading && (
                            <Loader2 className="inline w-3.5 h-3.5 ml-2 animate-spin text-gray-400" />
                        )}
                    </h2>
                    {history.length === 0 && !historyLoading ? (
                        <p className="text-sm text-gray-400 dark:text-gray-500">
                            履歴はありません。
                        </p>
                    ) : (
                        <div className="space-y-2">
                            {history.map((item) => (
                                <DiscussionHistoryItemCard
                                    key={item.filename}
                                    item={item}
                                    bookName={selectedBook}
                                    onDelete={handleDelete}
                                />
                            ))}
                        </div>
                    )}
                </section>
            )}
        </div>
    );
}
