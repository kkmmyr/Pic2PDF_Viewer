import { type CSSProperties } from 'react';
import { GripVertical } from 'lucide-react';
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { PdfCard, type PdfCardProps } from './PdfCard';

/** @dnd-kit useSortable ラッパー。ドラッグハンドルを右上に差し込む。 */
export function SortablePdfCard(props: PdfCardProps) {
    const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, transition, isDragging } = useSortable({
        id: props.pdf.name,
    });
    const style: CSSProperties = {
        transform: CSS.Transform.toString(transform),
        transition,
        opacity: isDragging ? 0.5 : 1,
        zIndex: isDragging ? 10 : 'auto',
    };
    // ドラッグハンドル単体に listeners を付け、カード本体のクリックは通常通り動かす。
    // setActivatorNodeRef でハンドルがドラッグ起点であることを明示する。
    // 位置は top-2 right-2（お気に入り星 top-2 left-2 との競合を避ける）。
    const handle = (
        <button
            ref={setActivatorNodeRef}
            {...listeners}
            onClick={(e) => e.stopPropagation()}
            className="absolute top-2 right-2 z-20 p-1 rounded-full bg-white/90 dark:bg-gray-900/80 text-gray-500 dark:text-gray-300 hover:text-purple-600 dark:hover:text-purple-300 cursor-grab active:cursor-grabbing shadow"
            title="ドラッグして並べ替え"
            aria-label={`${props.pdf.name} をドラッグ`}
        >
            <GripVertical className="w-4 h-4" />
        </button>
    );
    return (
        <div ref={setNodeRef} style={style} {...attributes}>
            <PdfCard {...props} dragHandle={handle} />
        </div>
    );
}
