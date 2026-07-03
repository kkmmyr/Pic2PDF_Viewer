import { type CSSProperties } from 'react';
import { CheckSquare, GripVertical, Square } from 'lucide-react';
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';

interface SortablePageCellProps {
    /** @dnd-kit/sortable で必要な一意 id（このセッション中だけ安定） */
    id: number;
    /** 表示するページ番号 / 削除マーク UI 用 */
    pageNumber: number;
    /** サムネイル URL（buildApiUrl 適用済み） */
    src: string;
    /** 削除マーク済みなら true */
    isSelected: boolean;
    onClick: (e: React.MouseEvent) => void;
}

/**
 * PageGridOverlay の各セル。@dnd-kit/sortable でドラッグ可能。
 *
 * - 左上に GripVertical のドラッグハンドル（ハンドル領域だけがドラッグ起点）
 * - カード本体クリックは onClick（選択トグル用）
 * - 既存 SortablePdfCard と同形のラッパーパターン
 */
export function SortablePageCell({
    id,
    pageNumber,
    src,
    isSelected,
    onClick,
}: SortablePageCellProps) {
    const {
        attributes,
        listeners,
        setNodeRef,
        setActivatorNodeRef,
        transform,
        transition,
        isDragging,
    } = useSortable({ id });

    const style: CSSProperties = {
        transform: CSS.Transform.toString(transform),
        transition,
        opacity: isDragging ? 0.4 : 1,
    };

    return (
        <div
            ref={setNodeRef}
            style={style}
            {...attributes}
            className={`relative ${isDragging ? 'z-card-badge' : ''}`}
        >
            <button
                type="button"
                onClick={onClick}
                aria-pressed={isSelected}
                className={`relative w-full bg-gray-700 rounded overflow-hidden focus:outline-none focus:ring-2 focus:ring-primary-500 transition-shadow ${
                    isSelected
                        ? 'ring-4 ring-red-500 shadow-xl'
                        : 'hover:ring-2 hover:ring-gray-500'
                }`}
            >
                <img
                    src={src}
                    alt={`Page ${pageNumber}`}
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
                    {pageNumber}
                </div>
            </button>
            {/* ハンドルは button の外に置く（button の中だと click 伝播で選択トグルが走るため）*/}
            <button
                ref={setActivatorNodeRef}
                {...listeners}
                onClick={(e) => e.stopPropagation()}
                className="absolute top-2 left-2 z-card-badge p-1 rounded-full bg-white/90 dark:bg-gray-900/80 text-gray-500 dark:text-gray-300 hover:text-accent-600 dark:hover:text-accent-300 cursor-grab active:cursor-grabbing shadow"
                title="ドラッグして並び替え"
                aria-label={`Page ${pageNumber} をドラッグ`}
            >
                <GripVertical className="w-4 h-4" />
            </button>
        </div>
    );
}
