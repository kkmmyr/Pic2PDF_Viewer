import { BookOpen, Users } from 'lucide-react';

import type { NovelBookGroup } from '../../hooks/useNovelLibraryGroup';
import type { GroupMode } from '../../hooks/useNovelLibraryGroup';

interface Props {
    group: NovelBookGroup;
    groupMode: GroupMode;
    onClick: () => void;
}

export default function SeriesGroupCard({ group, groupMode, onClick }: Props) {
    const { representative, books, label } = group;

    return (
        <button
            className="w-full text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-500 rounded-lg"
            onClick={onClick}
            aria-label={`${label} を開く`}
        >
            <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden bg-white dark:bg-gray-800 hover:border-accent-400 dark:hover:border-accent-500 transition-colors">
                <div className="relative">
                    {representative.thumbnail_url ? (
                        <img
                            src={representative.thumbnail_url}
                            alt={label}
                            className="w-full aspect-[3/4] object-cover bg-gray-100 dark:bg-gray-900 hover:opacity-90 transition-opacity"
                            loading="lazy"
                        />
                    ) : (
                        <div className="w-full aspect-[3/4] bg-gray-100 dark:bg-gray-900 flex items-center justify-center text-gray-400 text-sm">
                            画像なし
                        </div>
                    )}
                    {/* 冊数バッジ */}
                    <span className="absolute top-1.5 right-1.5 flex items-center gap-0.5 px-1.5 py-0.5 rounded-full bg-accent-600/90 text-white text-xs font-medium leading-none">
                        {groupMode === 'series' ? (
                            <BookOpen className="w-3 h-3" />
                        ) : (
                            <Users className="w-3 h-3" />
                        )}
                        {books.length}
                    </span>
                </div>
                <div className="p-2">
                    <p
                        className="text-xs font-medium text-gray-900 dark:text-gray-100 line-clamp-2 leading-snug"
                        title={label}
                    >
                        {label}
                    </p>
                    {representative.authors.length > 0 && (
                        <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 truncate">
                            {representative.authors[0]}
                        </p>
                    )}
                </div>
            </div>
        </button>
    );
}
