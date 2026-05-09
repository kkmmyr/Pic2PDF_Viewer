import { useEffect, useState, useCallback } from 'react';
import { X, Trash2, CheckSquare, Square } from 'lucide-react';
import { API_ENDPOINTS } from '../../config/api';
import type { LibrarySource } from '../../types';

interface PageGridOverlayProps {
    open: boolean;
    selectedPdf: string;
    currentPath: string;
    currentSource: LibrarySource;
    numPages: number;
    /** 削除実行後にインクリメントされる値。サムネ URL に付与してブラウザキャッシュを無効化 */
    pdfVersion: number;
    selectedPages: Set<number>;
    onClose: () => void;
    onTogglePage: (pNum: number, e: React.MouseEvent) => void;
    onSelectRange: (from: number, to: number) => void;
    /** 削除実行を要求（呼び出し側で確認ダイアログを表示） */
    onRequestDelete: () => void;
}

const THUMB_WIDTH = 180;

/**
 * 編集モード用の全画面オーバーレイ。
 *
 * - 全ページのサムネイルをグリッドで表示し、削除対象を複数マーク → 「削除実行」で一括コミット
 * - クリックで個別トグル / Shift+クリックで範囲選択
 * - サムネイルは既存 `GET /api/thumbnails/page` を流用（バックエンド改修なし）。
 *   `pdfVersion` を URL に含めることで削除後のブラウザキャッシュを無効化する
 * - Esc または `×` ボタンで閉じる（オーバーレイ背景クリックは誤操作防止のため無効）
 */
export function PageGridOverlay({
    open,
    selectedPdf,
    currentPath,
    currentSource,
    numPages,
    pdfVersion,
    selectedPages,
    onClose,
    onTogglePage,
    onSelectRange,
    onRequestDelete,
}: PageGridOverlayProps) {
    const [lastClickedPage, setLastClickedPage] = useState<number | null>(null);

    useEffect(() => {
        if (!open) {
            setLastClickedPage(null);
            return;
        }
        const handleKey = (e: KeyboardEvent) => {
            if (e.key === 'Escape') {
                e.preventDefault();
                onClose();
            }
        };
        window.addEventListener('keydown', handleKey);
        return () => window.removeEventListener('keydown', handleKey);
    }, [open, onClose]);

    const handleClick = useCallback(
        (pNum: number, e: React.MouseEvent) => {
            if (e.shiftKey && lastClickedPage !== null) {
                onSelectRange(lastClickedPage, pNum);
            } else {
                onTogglePage(pNum, e);
            }
            setLastClickedPage(pNum);
        },
        [lastClickedPage, onSelectRange, onTogglePage],
    );

    if (!open) return null;

    const pages = Array.from({ length: numPages }, (_, i) => i + 1);
    const selectedCount = selectedPages.size;

    return (
        <div className="fixed inset-0 z-dialog bg-gray-900/95 flex flex-col">
            {/* ヘッダー */}
            <div className="flex items-center justify-between px-6 py-3 border-b border-gray-700 bg-gray-800 text-gray-100">
                <div className="flex items-center gap-4">
                    <h2 className="text-lg font-semibold">{selectedPdf}</h2>
                    <span className="text-sm text-gray-400 tabular-nums">
                        全 {numPages} ページ / {selectedCount} 件選択中
                    </span>
                </div>
                <button
                    onClick={onClose}
                    className="p-2 hover:bg-gray-700 rounded-full"
                    title="閉じる (Esc)"
                >
                    <X className="w-5 h-5" />
                </button>
            </div>

            {/* グリッド本体 */}
            <div className="flex-1 overflow-auto p-6">
                <div
                    className="grid gap-4"
                    style={{
                        gridTemplateColumns: `repeat(auto-fill, minmax(${THUMB_WIDTH}px, 1fr))`,
                    }}
                >
                    {pages.map((pNum) => {
                        const isSelected = selectedPages.has(pNum);
                        const url = API_ENDPOINTS.PAGE_THUMBNAIL(
                            selectedPdf,
                            pNum,
                            currentPath,
                            currentSource,
                            THUMB_WIDTH,
                            pdfVersion,
                        );
                        return (
                            <button
                                key={pNum}
                                type="button"
                                onClick={(e) => handleClick(pNum, e)}
                                className={`relative bg-gray-700 rounded overflow-hidden focus:outline-none focus:ring-2 focus:ring-primary-500 transition-shadow ${
                                    isSelected
                                        ? 'ring-4 ring-red-500 shadow-xl'
                                        : 'hover:ring-2 hover:ring-gray-500'
                                }`}
                            >
                                <img
                                    src={url}
                                    alt={`Page ${pNum}`}
                                    loading="lazy"
                                    className="w-full h-auto block bg-white"
                                    draggable={false}
                                />
                                <div className="absolute top-2 right-2 z-card-badge bg-white rounded-full p-1 shadow-md">
                                    {isSelected ? (
                                        <CheckSquare className="w-5 h-5 text-red-500" />
                                    ) : (
                                        <Square className="w-5 h-5 text-gray-400" />
                                    )}
                                </div>
                                <div className="absolute bottom-1 left-1 px-1.5 py-0.5 text-xs font-mono bg-black/70 text-white rounded">
                                    {pNum}
                                </div>
                            </button>
                        );
                    })}
                </div>
            </div>

            {/* フッター */}
            <div className="flex items-center justify-between px-6 py-3 border-t border-gray-700 bg-gray-800 text-gray-100">
                <p className="text-xs text-gray-400">クリックで選択 / Shift + クリックで範囲選択</p>
                <button
                    onClick={onRequestDelete}
                    disabled={selectedCount === 0}
                    className="px-4 py-2 text-sm font-medium bg-red-600 text-white hover:bg-red-700 disabled:bg-gray-600 disabled:text-gray-400 disabled:cursor-not-allowed rounded-md transition-colors flex items-center gap-2"
                >
                    <Trash2 className="w-4 h-4" />
                    削除実行 ({selectedCount})
                </button>
            </div>
        </div>
    );
}
