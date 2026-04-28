import { CheckSquare, Square, Star, Pencil, RefreshCw, Library, EyeOff, Eye } from 'lucide-react';
import type { PdfFile } from '../../types';
import { LazyThumbnail } from './LazyThumbnail';

interface PdfGridProps {
    pdfs: PdfFile[];
    onPdfClick: (pdfName: string) => void;
    isSelectionMode?: boolean;
    selectedItems?: Set<string>;
    onToggleSelect?: (name: string) => void;
    favorites?: Set<string>;
    onToggleFavorite?: (name: string) => void;
    onRename?: (name: string) => void;
    onRegenThumb?: (name: string) => void;
    /** 書籍名 → 作者名リスト のマップ（カード下部に表示） */
    getAuthors?: (name: string) => string[];
    /** 作者タグクリック時に絞り込みを行うコールバック */
    onAuthorClick?: (author: string) => void;
    /** 書籍名 → タグリスト のマップ */
    getTags?: (name: string) => string[];
    /** タグクリック時に絞り込みを行うコールバック */
    onTagClick?: (tag: string) => void;
    /** シリーズ代表のメンバー数（バッジ表示用、null/0/1 の場合は非表示） */
    getSeriesCount?: (name: string) => number;
    /** シリーズ代表書籍をクリックしたときのハンドラ。指定されると onPdfClick より優先される */
    onSeriesClick?: (representativeName: string) => void;
    /** 「非表示にする」「再表示する」ボタンのハンドラ。
     *  - showHidden=false（通常モード）の時は EyeOff アイコンで「非表示にする」
     *  - showHidden=true（ゴミ箱モード）の時は Eye アイコンで「再表示する」
     */
    onToggleHidden?: (name: string) => void;
    /** ゴミ箱モード（true なら Eye アイコン、false なら EyeOff アイコンを表示） */
    showHidden?: boolean;
}

/**
 * PDF一覧のグリッド表示コンポーネント
 * - サムネイルは LazyThumbnail により Intersection Observer で遅延読み込み
 * - dark: クラスによるダークモード対応
 */
export function PdfGrid({
    pdfs,
    onPdfClick,
    isSelectionMode = false,
    selectedItems = new Set(),
    onToggleSelect,
    favorites = new Set(),
    onToggleFavorite,
    onRename,
    onRegenThumb,
    getAuthors,
    onAuthorClick,
    getTags,
    onTagClick,
    getSeriesCount,
    onSeriesClick,
    onToggleHidden,
    showHidden = false,
}: PdfGridProps) {
    if (pdfs.length === 0) {
        return (
            <div>
                <h2 className="text-lg font-semibold mb-4 text-gray-700 dark:text-gray-300">PDFs</h2>
                <p className="text-gray-500 dark:text-gray-400">No PDFs found.</p>
            </div>
        );
    }

    return (
        <div>
            <h2 className="text-lg font-semibold mb-4 text-gray-700 dark:text-gray-300">PDFs</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
                {pdfs.map((pdf) => {
                    const isFav = favorites.has(pdf.name);
                    const isSelected = isSelectionMode && selectedItems.has(pdf.name);
                    const seriesCount = getSeriesCount?.(pdf.name) ?? 0;
                    const isSeries = seriesCount > 1 && !!onSeriesClick;
                    return (
                        <div
                            key={pdf.name}
                            className={`rounded-lg shadow-md overflow-hidden hover:shadow-lg transition-shadow flex flex-col border-2 ${
                                isSelected
                                    ? 'border-amber-400 bg-amber-50 dark:bg-amber-900/20'
                                    : isSeries
                                        ? 'border-purple-300 dark:border-purple-700 bg-white dark:bg-gray-800'
                                        : 'border-transparent bg-white dark:bg-gray-800'
                            }`}
                        >
                            <div
                                className="aspect-[3/4] relative cursor-pointer"
                                onClick={() => {
                                    if (isSelectionMode && onToggleSelect) {
                                        onToggleSelect(pdf.name);
                                    } else if (isSeries && onSeriesClick) {
                                        onSeriesClick(pdf.name);
                                    } else {
                                        onPdfClick(pdf.name);
                                    }
                                }}
                            >
                                {/* 選択チェックボックス */}
                                {isSelectionMode && (
                                    <div className="absolute top-2 right-2 z-10 bg-white dark:bg-gray-800 rounded-full">
                                        {isSelected ? (
                                            <CheckSquare className="w-6 h-6 text-amber-500 fill-white" />
                                        ) : (
                                            <Square className="w-6 h-6 text-gray-400 fill-white" />
                                        )}
                                    </div>
                                )}

                                {/* シリーズバッジ（巻数表示） */}
                                {isSeries && (
                                    <div className="absolute top-2 right-2 z-10 px-1.5 py-0.5 rounded-full bg-purple-600 text-white text-xs font-semibold flex items-center gap-1 shadow">
                                        <Library className="w-3 h-3" />
                                        {seriesCount} 巻
                                    </div>
                                )}

                                {/* お気に入りボタン */}
                                {!isSelectionMode && onToggleFavorite && (
                                    <button
                                        className="absolute top-2 left-2 z-10 p-1 rounded-full bg-white/80 dark:bg-gray-900/70 hover:bg-white dark:hover:bg-gray-900 transition-colors"
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            onToggleFavorite(pdf.name);
                                        }}
                                        title={isFav ? 'お気に入りを解除' : 'お気に入りに追加'}
                                    >
                                        <Star
                                            className={`w-4 h-4 transition-colors ${
                                                isFav
                                                    ? 'text-amber-400 fill-amber-400'
                                                    : 'text-gray-300 dark:text-gray-500 hover:text-amber-300'
                                            }`}
                                        />
                                    </button>
                                )}

                                {/* 遅延読み込みサムネイル */}
                                <LazyThumbnail src={pdf.thumbnail} alt={pdf.name} className="absolute inset-0" />
                            </div>

                            <div className={`p-3 flex-1 flex flex-col justify-between ${isSelected ? 'bg-amber-50 dark:bg-amber-900/20' : 'bg-white dark:bg-gray-800'}`}>
                                <span className="font-medium text-sm text-gray-800 dark:text-gray-200 line-clamp-2" title={pdf.name}>
                                    {pdf.name.replace('.pdf', '')}
                                </span>
                                {/* 作者名タグ */}
                                {getAuthors && (() => {
                                    const authors = getAuthors(pdf.name);
                                    return authors.length > 0 ? (
                                        <div className="mt-1 flex flex-wrap gap-1">
                                            {authors.map((a, i) => (
                                                <span
                                                    key={i}
                                                    className={`text-xs px-1.5 py-0.5 rounded bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 truncate max-w-full ${onAuthorClick ? 'cursor-pointer hover:bg-blue-100 dark:hover:bg-blue-800/50' : ''}`}
                                                    onClick={onAuthorClick ? (e) => { e.stopPropagation(); onAuthorClick(a); } : undefined}
                                                    title={onAuthorClick ? `"${a}" で絞り込む` : undefined}
                                                >
                                                    {a}
                                                </span>
                                            ))}
                                        </div>
                                    ) : null;
                                })()}
                                {/* タグ */}
                                {getTags && (() => {
                                    const tags = getTags(pdf.name);
                                    return tags.length > 0 ? (
                                        <div className="mt-1 flex flex-wrap gap-1">
                                            {tags.map((t, i) => (
                                                <span
                                                    key={i}
                                                    className={`text-xs px-1.5 py-0.5 rounded bg-emerald-50 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300 truncate max-w-full ${onTagClick ? 'cursor-pointer hover:bg-emerald-100 dark:hover:bg-emerald-800/50' : ''}`}
                                                    onClick={onTagClick ? (e) => { e.stopPropagation(); onTagClick(t); } : undefined}
                                                    title={onTagClick ? `"${t}" で絞り込む` : undefined}
                                                >
                                                    #{t}
                                                </span>
                                            ))}
                                        </div>
                                    ) : null;
                                })()}
                                <div className="mt-2 flex items-center justify-between">
                                    <span className="text-xs text-gray-500 dark:text-gray-400">
                                        {pdf.created_at
                                            ? new Date(pdf.created_at * 1000).toLocaleDateString()
                                            : ''}
                                    </span>
                                    <div className="flex items-center gap-1">
                                        {!isSelectionMode && onRename && (
                                            <button
                                                onClick={(e) => { e.stopPropagation(); onRename(pdf.name); }}
                                                className="p-0.5 rounded hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-300 dark:text-gray-600 hover:text-gray-500 dark:hover:text-gray-400 transition-colors"
                                                title="名前を変更"
                                            >
                                                <Pencil className="w-3 h-3" />
                                            </button>
                                        )}
                                        {!isSelectionMode && onRegenThumb && (
                                            <button
                                                onClick={(e) => { e.stopPropagation(); onRegenThumb(pdf.name); }}
                                                className="p-0.5 rounded hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-300 dark:text-gray-600 hover:text-gray-500 dark:hover:text-gray-400 transition-colors"
                                                title="サムネイルを再生成"
                                            >
                                                <RefreshCw className="w-3 h-3" />
                                            </button>
                                        )}
                                        {!isSelectionMode && onToggleHidden && (
                                            <button
                                                onClick={(e) => { e.stopPropagation(); onToggleHidden(pdf.name); }}
                                                className="p-0.5 rounded hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-300 dark:text-gray-600 hover:text-gray-500 dark:hover:text-gray-400 transition-colors"
                                                title={showHidden ? '再表示する' : '非表示にする'}
                                            >
                                                {showHidden
                                                    ? <Eye className="w-3 h-3" />
                                                    : <EyeOff className="w-3 h-3" />}
                                            </button>
                                        )}
                                        {isFav && (
                                            <Star className="w-3 h-3 text-amber-400 fill-amber-400 shrink-0" />
                                        )}
                                    </div>
                                </div>
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
