import { CheckSquare, Square, Star } from 'lucide-react';
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
                    return (
                        <div
                            key={pdf.name}
                            className={`bg-white dark:bg-gray-800 rounded-lg shadow-md overflow-hidden hover:shadow-lg transition-shadow cursor-pointer flex flex-col border-2 ${
                                isSelectionMode && selectedItems.has(pdf.name)
                                    ? 'border-blue-500'
                                    : 'border-transparent'
                            }`}
                            onClick={() => {
                                if (isSelectionMode && onToggleSelect) {
                                    onToggleSelect(pdf.name);
                                } else {
                                    onPdfClick(pdf.name);
                                }
                            }}
                        >
                            <div className="aspect-[3/4] relative">
                                {/* 選択チェックボックス */}
                                {isSelectionMode && (
                                    <div className="absolute top-2 right-2 z-10 bg-white dark:bg-gray-800 rounded-full">
                                        {selectedItems.has(pdf.name) ? (
                                            <CheckSquare className="w-6 h-6 text-blue-500 fill-white" />
                                        ) : (
                                            <Square className="w-6 h-6 text-gray-400 fill-white" />
                                        )}
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

                            <div className="p-3 bg-white dark:bg-gray-800 flex-1 flex flex-col justify-between">
                                <span className="font-medium text-sm text-gray-800 dark:text-gray-200 line-clamp-2" title={pdf.name}>
                                    {pdf.name.replace('.pdf', '')}
                                </span>
                                <div className="mt-2 flex items-center justify-between">
                                    <span className="text-xs text-gray-500 dark:text-gray-400">
                                        {pdf.created_at
                                            ? new Date(pdf.created_at * 1000).toLocaleDateString()
                                            : ''}
                                    </span>
                                    {isFav && (
                                        <Star className="w-3 h-3 text-amber-400 fill-amber-400 shrink-0" />
                                    )}
                                </div>
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
