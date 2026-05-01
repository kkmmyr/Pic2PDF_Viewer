import { Search, User, Tag } from 'lucide-react';
import { SearchableSelect } from '../ui/SearchableSelect';

/** ジャンルボタンの表示順。リストにないジャンルはアルファベット順で末尾に追加される */
const GENRE_ORDER = ['オリジナル', 'プリンセスコネクト', 'Voiceloid'];

interface HeaderSearchBarProps {
    searchText: string;
    authorFilter: string;
    tagFilter: string;
    genreFilter: string;
    allAuthors: string[];
    allTags: string[];
    allGenres: string[];
    /** ドリルダウン中はパンくずに集約するため作者 select を隠す */
    hideAuthorSelect?: boolean;
    onSearchChange: (text: string) => void;
    onAuthorFilterChange: (author: string) => void;
    onTagFilterChange: (tag: string) => void;
    onGenreFilterChange: (genre: string) => void;
}

export function HeaderSearchBar({
    searchText,
    authorFilter,
    tagFilter,
    genreFilter,
    allAuthors,
    allTags,
    allGenres,
    hideAuthorSelect = false,
    onSearchChange,
    onAuthorFilterChange,
    onTagFilterChange,
    onGenreFilterChange,
}: HeaderSearchBarProps) {
    const sortedGenres = [...allGenres].sort((a, b) => {
        const ai = GENRE_ORDER.indexOf(a);
        const bi = GENRE_ORDER.indexOf(b);
        if (ai !== -1 && bi !== -1) return ai - bi;
        if (ai !== -1) return -1;
        if (bi !== -1) return 1;
        return a.localeCompare(b, 'ja');
    });

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

            {sortedGenres.length > 0 && (
                <div className="flex items-center gap-1">
                    <button
                        onClick={() => onGenreFilterChange('')}
                        className={`px-2.5 py-0.5 rounded-full text-xs font-medium transition-colors whitespace-nowrap ${
                            !genreFilter
                                ? 'bg-blue-600 text-white'
                                : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
                        }`}
                    >
                        すべて
                    </button>
                    {sortedGenres.map(g => (
                        <button
                            key={g}
                            onClick={() => onGenreFilterChange(genreFilter === g ? '' : g)}
                            className={`px-2.5 py-0.5 rounded-full text-xs font-medium transition-colors whitespace-nowrap ${
                                genreFilter === g
                                    ? 'bg-blue-600 text-white'
                                    : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
                            }`}
                        >
                            {g}
                        </button>
                    ))}
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
