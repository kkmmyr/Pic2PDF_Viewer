import { Search, User, Tag } from 'lucide-react';

interface HeaderSearchBarProps {
    searchText: string;
    authorFilter: string;
    tagFilter: string;
    allAuthors: string[];
    allTags: string[];
    onSearchChange: (text: string) => void;
    onAuthorFilterChange: (author: string) => void;
    onTagFilterChange: (tag: string) => void;
}

export function HeaderSearchBar({
    searchText,
    authorFilter,
    tagFilter,
    allAuthors,
    allTags,
    onSearchChange,
    onAuthorFilterChange,
    onTagFilterChange,
}: HeaderSearchBarProps) {
    return (
        <>
            <div className="relative">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400 dark:text-gray-500 pointer-events-none" />
                <input
                    type="text"
                    value={searchText}
                    onChange={(e) => onSearchChange(e.target.value)}
                    placeholder="タイトル / 作者 / タグを検索..."
                    className="pl-8 pr-3 py-1.5 text-sm border border-gray-200 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-200 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-400 w-56"
                />
            </div>

            {allAuthors.length > 0 && (
                <div className="flex items-center gap-1 text-sm text-gray-600 dark:text-gray-400">
                    <User className="w-4 h-4 text-gray-400 dark:text-gray-500 shrink-0" />
                    <select
                        value={authorFilter}
                        onChange={(e) => onAuthorFilterChange(e.target.value)}
                        className="border border-gray-200 dark:border-gray-600 rounded-md px-2 py-1 text-sm text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-400 max-w-[200px] truncate"
                    >
                        <option value="">作者: すべて</option>
                        {allAuthors.map(a => (
                            <option key={a} value={a}>{a}</option>
                        ))}
                    </select>
                </div>
            )}

            {allTags.length > 0 && (
                <div className="flex items-center gap-1 text-sm text-gray-600 dark:text-gray-400">
                    <Tag className="w-4 h-4 text-gray-400 dark:text-gray-500 shrink-0" />
                    <select
                        value={tagFilter}
                        onChange={(e) => onTagFilterChange(e.target.value)}
                        className="border border-gray-200 dark:border-gray-600 rounded-md px-2 py-1 text-sm text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-400 max-w-[200px] truncate"
                    >
                        <option value="">タグ: すべて</option>
                        {allTags.map(t => (
                            <option key={t} value={t}>#{t}</option>
                        ))}
                    </select>
                </div>
            )}
        </>
    );
}
