import { LayoutGrid, Users, BookOpen, CheckSquare, Square } from 'lucide-react';
import type { GroupMode } from '@/hooks/useNovelLibraryGroup';

const GROUP_MODES: { value: GroupMode; label: string; icon: React.ReactNode }[] = [
    { value: 'flat', label: 'フラット', icon: <LayoutGrid className="w-3.5 h-3.5" /> },
    { value: 'author', label: '作者別', icon: <Users className="w-3.5 h-3.5" /> },
    { value: 'series', label: 'シリーズ別', icon: <BookOpen className="w-3.5 h-3.5" /> },
];

interface Props {
    groupMode: GroupMode;
    totalCount: number;
    isSelecting: boolean;
    onChangeMode: (mode: GroupMode) => void;
    onToggleSelecting: () => void;
}

export function LibraryViewModeSelector({
    groupMode,
    totalCount,
    isSelecting,
    onChangeMode,
    onToggleSelecting,
}: Props) {
    return (
        <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mr-2">
                ライブラリ ({totalCount} 冊)
            </h2>

            <div className="flex rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden text-xs">
                {GROUP_MODES.map(({ value, label, icon }) => (
                    <button
                        key={value}
                        onClick={() => onChangeMode(value)}
                        className={`flex items-center gap-1 px-2.5 py-1.5 transition-colors ${
                            groupMode === value
                                ? 'bg-primary-600 text-white'
                                : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
                        }`}
                    >
                        {icon}
                        {label}
                    </button>
                ))}
            </div>

            <button
                onClick={onToggleSelecting}
                className={`flex items-center gap-1 text-xs px-2.5 py-1.5 rounded-lg border transition-colors ${
                    isSelecting
                        ? 'bg-primary-100 dark:bg-primary-900/40 border-primary-400 text-primary-700 dark:text-primary-300'
                        : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
                }`}
            >
                {isSelecting ? (
                    <CheckSquare className="w-3.5 h-3.5" />
                ) : (
                    <Square className="w-3.5 h-3.5" />
                )}
                選択
            </button>
        </div>
    );
}
