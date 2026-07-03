import { DndContext, closestCenter, PointerSensor, useSensor, useSensors } from '@dnd-kit/core';
import { SortableContext, rectSortingStrategy, useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { GripVertical } from 'lucide-react';

import type { BookSummary } from '@/features/novel_db/types';
import { useSeriesDrilldownReorder } from '@/hooks/novel_db';
import BookCard from './BookCard';

interface Props {
    seriesId: string;
    books: BookSummary[];
    onOpenDetailBook: (bookName: string) => void;
    onEditBook: (book: BookSummary) => void;
    onReordered: () => void;
}

export default function SeriesDrilldownView({
    seriesId,
    books: initialBooks,
    onOpenDetailBook,
    onEditBook,
    onReordered,
}: Props) {
    const { books, handleDragEnd } = useSeriesDrilldownReorder(seriesId, initialBooks, onReordered);

    const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));

    return (
        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
            <SortableContext items={books.map((b) => b.name)} strategy={rectSortingStrategy}>
                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3">
                    {books.map((book) => (
                        <SortableBookCard
                            key={book.name}
                            book={book}
                            onOpenDetail={onOpenDetailBook}
                            onEdit={onEditBook}
                        />
                    ))}
                </div>
            </SortableContext>
        </DndContext>
    );
}

interface SortableBookCardProps {
    book: BookSummary;
    onOpenDetail: (bookName: string) => void;
    onEdit: (book: BookSummary) => void;
}

function SortableBookCard({ book, onOpenDetail, onEdit }: SortableBookCardProps) {
    const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
        id: book.name,
    });

    const style = {
        transform: CSS.Transform.toString(transform),
        transition,
        opacity: isDragging ? 0.5 : 1,
    };

    return (
        <div
            ref={setNodeRef}
            style={style}
            className={`relative ${isDragging ? 'z-card-badge' : ''}`}
        >
            {/* ドラッグハンドル */}
            <div
                {...attributes}
                {...listeners}
                className="absolute top-1 left-1 z-card-badge p-0.5 rounded bg-white/80 dark:bg-gray-900/80 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 cursor-grab active:cursor-grabbing touch-none"
                aria-label="ドラッグして並び替え"
            >
                <GripVertical className="w-3.5 h-3.5" />
            </div>
            <BookCard book={book} onOpenDetail={onOpenDetail} onEdit={onEdit} />
        </div>
    );
}
