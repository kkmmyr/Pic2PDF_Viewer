import { useEffect, useState, useCallback } from 'react';
import { X, Trash2 } from 'lucide-react';
import { DndContext, PointerSensor, useSensor, useSensors, type DragEndEvent } from '@dnd-kit/core';
import { SortableContext, arrayMove, rectSortingStrategy } from '@dnd-kit/sortable';
import { API_ENDPOINTS, buildApiUrl } from '@/config/api';
import { moveMultipleByIndex } from '@/utils/sort';
import type { LibrarySource } from '@/types';
import { SortablePageCell } from './SortablePageCell';

interface PageGridOverlayProps {
    open: boolean;
    selectedPdf: string;
    currentPath: string;
    currentSource: LibrarySource;
    numPages: number;
    /** 削除/並び替え実行後にインクリメントされる値。サムネ URL に付与してブラウザキャッシュを無効化 */
    pdfVersion: number;
    selectedPages: Set<number>;
    onClose: () => void;
    onTogglePage: (pNum: number, e: React.MouseEvent) => void;
    onSelectRange: (from: number, to: number) => void;
    /** 削除実行を要求（呼び出し側で確認ダイアログを表示） */
    onRequestDelete: () => void;
    /**
     * ページを並び替える（B-3）。
     * `newOrder[i]` は新しい位置 i+1 に配置する元の 1 始まりページ番号。
     * 戻り値: 成功なら true / 失敗なら false（呼び出し側で楽観的更新をリバート）
     */
    onApplyReorder: (newOrder: number[]) => Promise<boolean>;
}

const THUMB_WIDTH = 180;

const buildIdentity = (n: number): number[] => Array.from({ length: n }, (_, i) => i + 1);

/**
 * 編集モード用の全画面オーバーレイ。
 *
 * - 全ページのサムネイルをグリッドで表示し、削除対象を複数マーク → 「削除実行」で一括コミット
 * - クリックで個別トグル / Shift+クリックで範囲選択
 * - サムネイルは既存 `GET /api/thumbnails/page` を流用（バックエンド改修なし）。
 *   `pdfVersion` を URL に含めることで削除/並び替え後のブラウザキャッシュを無効化する
 * - 各カード左上の GripVertical ハンドルから DnD でページ並び替え（B-3）。
 *   未選択カード起点 = 単独移動 / 選択済みカード起点 = 選択中をまとめて移動
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
    onApplyReorder,
}: PageGridOverlayProps) {
    const [lastClickedPage, setLastClickedPage] = useState<number | null>(null);
    // localOrder[displayPos] = "現在の backend state における 1 始まりページ番号"
    // 楽観的更新中はドラッグ後の順序を保持し、applyReorder 成功時に identity にリセットする。
    // numPages / pdfVersion 変化時もリセット（safety net）。
    const [localOrder, setLocalOrder] = useState<number[]>(() => buildIdentity(numPages));

    useEffect(() => {
        setLocalOrder(buildIdentity(numPages));
    }, [numPages, pdfVersion, open]);

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

    // PointerSensor: 8px のしきい値を入れて、ハンドルクリックでの誤発火を防ぐ
    const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 8 } }));

    const handleDragEnd = useCallback(
        async (event: DragEndEvent) => {
            const { active, over } = event;
            if (!over || active.id === over.id) return;

            const activePage = active.id as number;
            const overPage = over.id as number;
            const activeIdx = localOrder.indexOf(activePage);
            const overIdx = localOrder.indexOf(overPage);
            if (activeIdx < 0 || overIdx < 0) return;

            // 起点が選択済みなら、選択中の全ページを元の相対順を保ったまま移動（グループ drag）
            const isGroupDrag = selectedPages.has(activePage);
            let newOrder: number[];
            if (isGroupDrag) {
                const movedIndices = localOrder
                    .map((p, i) => (selectedPages.has(p) ? i : -1))
                    .filter((i) => i >= 0);
                // AT 方式: active が targetIndex に着地するようグループ全体を配置する
                // （単独移動の場合 arrayMove と等価になる）
                newOrder = moveMultipleByIndex(localOrder, movedIndices, activeIdx, overIdx);
            } else {
                newOrder = arrayMove(localOrder, activeIdx, overIdx);
            }

            // 楽観的 visual update
            const previousOrder = localOrder;
            setLocalOrder(newOrder);

            const ok = await onApplyReorder(newOrder);
            if (ok) {
                // 並び替え確定後、localOrder を identity にリセット
                // （applyReorder 内で bumpPdfVersion されているため URL も新版に切り替わる）
                setLocalOrder(buildIdentity(numPages));
            } else {
                // 失敗時は元の表示に戻す
                setLocalOrder(previousOrder);
            }
        },
        [localOrder, selectedPages, numPages, onApplyReorder],
    );

    if (!open) return null;

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
                <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
                    <SortableContext items={localOrder} strategy={rectSortingStrategy}>
                        <div
                            className="grid gap-4"
                            style={{
                                gridTemplateColumns: `repeat(auto-fill, minmax(${THUMB_WIDTH}px, 1fr))`,
                            }}
                        >
                            {localOrder.map((origPage, displayIdx) => {
                                const url = buildApiUrl(
                                    API_ENDPOINTS.PAGE_THUMBNAIL(
                                        selectedPdf,
                                        origPage,
                                        currentPath,
                                        currentSource,
                                        THUMB_WIDTH,
                                        pdfVersion,
                                    ),
                                );
                                return (
                                    <SortablePageCell
                                        key={origPage}
                                        id={origPage}
                                        pageNumber={displayIdx + 1}
                                        src={url}
                                        isSelected={selectedPages.has(origPage)}
                                        onClick={(e) => handleClick(origPage, e)}
                                    />
                                );
                            })}
                        </div>
                    </SortableContext>
                </DndContext>
            </div>

            {/* フッター */}
            <div className="flex items-center justify-between px-6 py-3 border-t border-gray-700 bg-gray-800 text-gray-100">
                <p className="text-xs text-gray-400">
                    クリックで選択 / Shift + クリックで範囲選択 / ハンドルでドラッグ並び替え
                </p>
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
