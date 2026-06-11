import { Search, User } from 'lucide-react';
import { SearchableSelect } from '@/components/ui/SearchableSelect';

interface HeaderSearchBarProps {
    searchText: string;
    authorFilter: string;
    allAuthors: string[];
    /** ドリルダウン中はパンくずに集約するため作者 select を隠す */
    hideAuthorSelect?: boolean;
    onSearchChange: (text: string) => void;
    onAuthorFilterChange: (author: string) => void;
}

export function HeaderSearchBar({
    searchText,
    authorFilter,
    allAuthors,
    hideAuthorSelect = false,
    onSearchChange,
    onAuthorFilterChange,
}: HeaderSearchBarProps) {
    return (
        <>
            <div className="relative">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400 dark:text-gray-500 pointer-events-none" />
                <input
                    type="text"
                    value={searchText}
                    onChange={(e) => onSearchChange(e.target.value)}
                    placeholder="タイトル / 作者を検索..."
                    className="pl-8 pr-3 py-1.5 text-sm border border-gray-200 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-200 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-400 w-56"
                />
            </div>

            {allAuthors.length > 0 && !hideAuthorSelect && (
                <div className="flex items-center gap-1 text-sm text-gray-600 dark:text-gray-400">
                    <User className="w-4 h-4 text-gray-400 dark:text-gray-500 shrink-0" />
                    <SearchableSelect
                        value={authorFilter}
                        options={allAuthors}
                        emptyLabel="作者: すべて"
                        placeholder="作者名で絞り込み"
                        onChange={onAuthorFilterChange}
                        className="w-48"
                    />
                </div>
            )}
        </>
    );
}
