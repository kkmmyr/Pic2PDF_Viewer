/**
 * B-20 読書会ディスカッション生成ページ（/novel/discussion）。
 *
 * ロジックは useDiscussion フックに委譲し、このページは JSX の
 * オーケストレーターのみとなっている。
 */
import { Loader2, MessageSquare, Square } from 'lucide-react';

import DiscussionHistoryItemCard, { TurnCard } from '@/components/novel_db/DiscussionHistoryItem';
import PersonaPanel from '@/components/novel_db/PersonaPanel';
import { useDiscussion } from '@/hooks/novel_db/useDiscussion';
import { useNovelDbBooks } from '@/hooks/novel_db';

export default function NovelDiscussionPage() {
    const { books } = useNovelDbBooks();
    const {
        selectedBook,
        setSelectedBook,
        personaA,
        setPersonaA,
        personaB,
        setPersonaB,
        numTurns,
        setNumTurns,
        turns,
        isGenerating,
        error,
        nameA,
        nameB,
        canGenerate,
        history,
        historyLoading,
        handleGenerate,
        handleCancel,
        bottomRef,
    } = useDiscussion();

    return (
        <div className="max-w-3xl mx-auto px-4 sm:px-6 py-6 space-y-6">
            {/* ヘッダー */}
            <div className="flex items-center gap-2">
                <MessageSquare className="w-5 h-5 text-indigo-500" />
                <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100">
                    読書会ディスカッション
                </h1>
            </div>

            {/* 設定パネル */}
            <div className="space-y-4 border border-gray-200 dark:border-gray-700 rounded-xl p-4">
                {/* 書籍選択 */}
                <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                        書籍を選択
                    </label>
                    <select
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

                {/* ペルソナ設定 */}
                <div className="flex gap-3">
                    <PersonaPanel
                        label="キャラクター A"
                        persona={personaA}
                        onChange={setPersonaA}
                        disabled={isGenerating}
                    />
                    <PersonaPanel
                        label="キャラクター B"
                        persona={personaB}
                        onChange={setPersonaB}
                        disabled={isGenerating}
                    />
                </div>

                {/* 発話数スライダー */}
                <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                        往復数:{' '}
                        <span className="text-indigo-600 dark:text-indigo-400">{numTurns}</span>{' '}
                        往復 （合計 {numTurns * 2} 発言）
                    </label>
                    <input
                        type="range"
                        min={2}
                        max={20}
                        step={1}
                        value={numTurns}
                        onChange={(e) => setNumTurns(Number(e.target.value))}
                        disabled={isGenerating}
                        className="w-full accent-indigo-600 disabled:opacity-50"
                    />
                    <div className="flex justify-between text-xs text-gray-400 mt-0.5">
                        <span>2往復</span>
                        <span>20往復</span>
                    </div>
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
                                <MessageSquare className="w-4 h-4" />
                                読書会を生成
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
                    <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300">
                        生成結果
                        {isGenerating && (
                            <span className="ml-2 text-xs text-gray-400 font-normal">
                                生成中...
                            </span>
                        )}
                    </h2>
                    <div className="space-y-3">
                        {turns.map((t, i) => (
                            <TurnCard
                                key={i}
                                speaker={t.speaker}
                                text={t.text}
                                nameA={nameA}
                                nameB={nameB}
                            />
                        ))}
                        <div ref={bottomRef} />
                    </div>
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
                                <DiscussionHistoryItemCard key={item.filename} item={item} />
                            ))}
                        </div>
                    )}
                </section>
            )}
        </div>
    );
}
