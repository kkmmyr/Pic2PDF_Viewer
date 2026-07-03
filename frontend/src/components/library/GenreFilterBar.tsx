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
        'px-4 py-1.5 rounded-md text-sm font-medium transition-colors whitespace-nowrap border select-none';
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
            <div className="shrink-0 border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-4 py-2 flex items-center gap-2">
                <button
                    onClick={() => setIsManagerOpen(true)}
                    title="ジャンルを管理"
                    className="p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-400 dark:text-gray-500"
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
        <div className="shrink-0 border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-4 py-2 flex items-center gap-2">
            <button
                onClick={() => setIsManagerOpen(true)}
                title="ジャンルを管理"
                className="p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-400 dark:text-gray-500 shrink-0"
            >
                <Settings2 className="w-4 h-4" />
            </button>

            {/* すべて */}
            <button
                onClick={() => setGenreFilter('')}
                className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors whitespace-nowrap border shrink-0 ${
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
                    <div className="flex items-center gap-2 overflow-x-auto">
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
