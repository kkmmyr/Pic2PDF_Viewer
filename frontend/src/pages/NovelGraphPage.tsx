/**
 * C-12: キャラクタ関係グラフページ（/novel/graph）。
 *
 * シリーズを選択 → vis-network でインタラクティブなキャラクタ関係グラフを描画する。
 * 冊フィルタで表示範囲を絞り込み可能。ノードクリックでキャラ名をサイドパネルに表示。
 */
import { useState } from 'react';
import { Share2 } from 'lucide-react';
import CharacterGraph from '@/components/novel_graph/CharacterGraph';
import { useCharacterGraph } from '@/hooks/novel_graph/useCharacterGraph';

export default function NovelGraphPage() {
    const {
        seriesList,
        selectedSeries,
        setSelectedSeries,
        books,
        selectedBookIds,
        toggleBook,
        graphData,
        loading,
        error,
    } = useCharacterGraph();

    const [clickedChar, setClickedChar] = useState<string | null>(null);

    return (
        <div className="flex flex-col h-full gap-4 p-4">
            <h1 className="text-lg font-semibold flex items-center gap-2">
                <Share2 size={20} />
                キャラクタ関係グラフ
            </h1>

            {/* シリーズ選択 */}
            <div className="flex items-center gap-3 flex-shrink-0">
                <label
                    htmlFor="graph-series-select"
                    className="text-sm font-medium whitespace-nowrap"
                >
                    シリーズ
                </label>
                <select
                    id="graph-series-select"
                    className="border rounded px-2 py-1 text-sm bg-white dark:bg-gray-800 dark:border-gray-600 flex-1 max-w-xs"
                    value={selectedSeries ?? ''}
                    onChange={(e) => {
                        setSelectedSeries(e.target.value || null);
                        setClickedChar(null);
                    }}
                >
                    <option value="">-- 選択してください --</option>
                    {seriesList.map((s) => (
                        <option key={s} value={s}>
                            {s}
                        </option>
                    ))}
                </select>
                {seriesList.length === 0 && (
                    <span className="text-xs text-gray-400">
                        ※ 関係グラフ生成済みのシリーズがありません（管理ページから生成してください）
                    </span>
                )}
            </div>

            {selectedSeries && books.length > 0 && (
                <div className="flex flex-wrap gap-2 flex-shrink-0">
                    <span className="text-sm font-medium self-center">冊フィルタ:</span>
                    {books.map((b) => (
                        <label
                            key={b.id}
                            className="flex items-center gap-1 text-sm cursor-pointer"
                        >
                            <input
                                type="checkbox"
                                checked={selectedBookIds.includes(b.id)}
                                onChange={() => toggleBook(b.id)}
                                className="accent-indigo-500"
                            />
                            <span className="max-w-[200px] truncate" title={b.name}>
                                {b.name}
                            </span>
                        </label>
                    ))}
                </div>
            )}

            <div className="flex flex-1 gap-4 min-h-0">
                {/* グラフエリア */}
                <div className="flex-1 border rounded-lg overflow-hidden bg-white dark:bg-gray-900 relative">
                    {loading && (
                        <div className="absolute inset-0 flex items-center justify-center bg-white/70 dark:bg-gray-900/70 z-10">
                            <span className="text-sm text-gray-500">読み込み中...</span>
                        </div>
                    )}
                    {error && (
                        <div className="absolute inset-0 flex items-center justify-center">
                            <span className="text-sm text-red-500">{error}</span>
                        </div>
                    )}
                    {!selectedSeries && !loading && (
                        <div className="absolute inset-0 flex items-center justify-center">
                            <span className="text-sm text-gray-400">
                                シリーズを選択してください
                            </span>
                        </div>
                    )}
                    {graphData && graphData.nodes.length > 0 && (
                        <CharacterGraph data={graphData} onNodeClick={setClickedChar} />
                    )}
                    {graphData && graphData.nodes.length === 0 && !loading && (
                        <div className="absolute inset-0 flex items-center justify-center">
                            <span className="text-sm text-gray-400">
                                選択した冊にグラフデータがありません
                            </span>
                        </div>
                    )}
                </div>

                {/* サイドパネル: クリックしたキャラ名 */}
                {clickedChar && (
                    <div className="w-56 border rounded-lg p-3 bg-white dark:bg-gray-900 flex-shrink-0">
                        <p className="text-xs text-gray-400 mb-1">選択キャラクタ</p>
                        <p className="font-semibold text-indigo-600 dark:text-indigo-400">
                            {clickedChar}
                        </p>
                        <button
                            className="mt-3 text-xs text-gray-400 hover:text-gray-600"
                            onClick={() => setClickedChar(null)}
                        >
                            閉じる
                        </button>
                    </div>
                )}
            </div>
        </div>
    );
}
