import { Search } from 'lucide-react';
import { cn } from '@/lib/utils';

interface HeaderSearchBarProps {
    searchText: string;
    onSearchChange: (text: string) => void;
    className?: string;
}

export function HeaderSearchBar({ searchText, onSearchChange, className }: HeaderSearchBarProps) {
    return (
        <div className={cn('relative min-w-0', className)}>
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-500 dark:text-gray-400" />
            <input
                type="search"
                value={searchText}
                onChange={(e) => onSearchChange(e.target.value)}
                aria-label="書籍を検索"
                placeholder="タイトル / 作者を検索…"
                className="min-h-11 w-full rounded-lg border border-gray-300 bg-white py-2 pl-9 pr-3 text-sm text-gray-800 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-primary-500 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200 dark:placeholder-gray-400 lg:min-h-9 lg:py-1.5"
            />
        </div>
    );
}
