import { useState } from 'react';
import { Settings2 } from 'lucide-react';
import {
    DndContext,
    closestCenter,
    PointerSensor,
    KeyboardSensor,
    useSensor,
    useSensors,
    type DragEndEvent,
} from '@dnd-kit/core';
import {
    SortableContext,
    horizontalListSortingStrategy,
    useSortable,
    arrayMove,
    sortableKeyboardCoordinates,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { GenreManagerDialog } from './GenreManagerDialog';
import { useLibraryPanelContext } from '@/contexts/LibraryPanelContext';

interface SortableGenrePillProps {
    genre: string;
    isActive: boolean;
    onClick: () => void;
}

function SortableGenrePill({ genre, isActive, onClick }: SortableGenrePillProps) {
    const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
        id: genre,
    });

    const style = {
        transform: CSS.Transform.toString(transform),
        transition,
        opacity: isDragging ? 0.5 : 1,
        cursor: isDragging ? 'grabbing' : 'grab',
    };

    const btnBase =
        'min-h-11 lg:min-h-0 px-4 py-1.5 rounded-md text-sm font-medium transition-colors whitespace-nowrap border select-none';
    const btnActive = 'bg-indigo-600 text-white border-indigo-600';
    const btnInactive =
        'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 border-gray-200 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700';

    return (
        <div
            ref={setNodeRef}
            style={style}
            {...attributes}
            {...listeners}
            onClick={onClick}
            className={`${btnBase} ${isActive ? btnActive : btnInactive}`}
        >
            {genre}
        </div>
    );
}

export function GenreFilterBar() {
    const { genres, genreFilter, setGenreFilter, reorderGenres, addGenre, removeGenre } =
        useLibraryPanelContext();
    const [isManagerOpen, setIsManagerOpen] = useState(false);

    const sensors = useSensors(
        useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
        useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
    );

    const handleDragEnd = (event: DragEndEvent) => {
        const { active, over } = event;
        if (!over || active.id === over.id) return;
        const oldIndex = genres.indexOf(active.id as string);
        const newIndex = genres.indexOf(over.id as string);
        if (oldIndex !== -1 && newIndex !== -1) {
            reorderGenres(arrayMove(genres, oldIndex, newIndex));
        }
    };

    if (genres.length === 0) {
        return (
            <div className="flex shrink-0 items-center gap-2 overflow-hidden border-b border-gray-200 bg-white px-4 py-2 dark:border-gray-700 dark:bg-gray-900">
                <button
                    onClick={() => setIsManagerOpen(true)}
                    title="ジャンルを管理"
                    aria-label="ジャンルを管理"
                    className="flex min-h-11 min-w-11 items-center justify-center rounded text-gray-500 hover:bg-gray-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 dark:text-gray-400 dark:hover:bg-gray-800 lg:min-h-8 lg:min-w-8"
                >
                    <Settings2 className="w-4 h-4" />
                </button>
                <GenreManagerDialog
                    open={isManagerOpen}
                    genres={genres}
                    onClose={() => setIsManagerOpen(false)}
                    onAdd={addGenre}
                    onRemove={removeGenre}
                />
            </div>
        );
    }

    return (
        <div className="flex shrink-0 items-center gap-2 overflow-hidden border-b border-gray-200 bg-white px-4 py-2 dark:border-gray-700 dark:bg-gray-900">
            <button
                onClick={() => setIsManagerOpen(true)}
                title="ジャンルを管理"
                aria-label="ジャンルを管理"
                className="flex min-h-11 min-w-11 shrink-0 items-center justify-center rounded text-gray-500 hover:bg-gray-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 dark:text-gray-400 dark:hover:bg-gray-800 lg:min-h-8 lg:min-w-8"
            >
                <Settings2 className="w-4 h-4" />
            </button>

            {/* すべて */}
            <button
                onClick={() => setGenreFilter('')}
                className={`min-h-11 lg:min-h-0 px-4 py-1.5 rounded-md text-sm font-medium transition-colors whitespace-nowrap border shrink-0 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 ${
                    !genreFilter
                        ? 'bg-indigo-600 text-white border-indigo-600'
                        : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 border-gray-200 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700'
                }`}
            >
                すべて
            </button>

            <DndContext
                sensors={sensors}
                collisionDetection={closestCenter}
                onDragEnd={handleDragEnd}
            >
                <SortableContext items={genres} strategy={horizontalListSortingStrategy}>
                    <div className="flex min-w-0 flex-1 items-center gap-2 overflow-x-auto overscroll-x-contain">
                        {genres.map((genre) => (
                            <SortableGenrePill
                                key={genre}
                                genre={genre}
                                isActive={genreFilter === genre}
                                onClick={() => setGenreFilter(genreFilter === genre ? '' : genre)}
                            />
                        ))}
                    </div>
                </SortableContext>
            </DndContext>

            <GenreManagerDialog
                open={isManagerOpen}
                genres={genres}
                onClose={() => setIsManagerOpen(false)}
                onAdd={addGenre}
                onRemove={removeGenre}
            />
        </div>
    );
}
