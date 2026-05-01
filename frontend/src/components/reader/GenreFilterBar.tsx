import { Layers } from 'lucide-react';

const GENRE_ORDER = ['オリジナル', 'プリンセスコネクト', 'Voiceloid'];

interface GenreFilterBarProps {
    allGenres: string[];
    genreFilter: string;
    onGenreFilterChange: (genre: string) => void;
}

export function GenreFilterBar({ allGenres, genreFilter, onGenreFilterChange }: GenreFilterBarProps) {
    if (allGenres.length === 0) return null;

    const sortedGenres = [...allGenres].sort((a, b) => {
        const ai = GENRE_ORDER.indexOf(a);
        const bi = GENRE_ORDER.indexOf(b);
        if (ai !== -1 && bi !== -1) return ai - bi;
        if (ai !== -1) return -1;
        if (bi !== -1) return 1;
        return a.localeCompare(b, 'ja');
    });

    const btnBase = 'px-4 py-1.5 rounded-md text-sm font-medium transition-colors whitespace-nowrap border';
    const btnActive = 'bg-indigo-600 text-white border-indigo-600';
    const btnInactive = 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 border-gray-200 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700';

    return (
        <div className="shrink-0 border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-4 py-2 flex items-center gap-2">
            <Layers className="w-4 h-4 text-gray-400 dark:text-gray-500 shrink-0" />
            <button
                onClick={() => onGenreFilterChange('')}
                className={`${btnBase} ${!genreFilter ? btnActive : btnInactive}`}
            >
                すべて
            </button>
            {sortedGenres.map(g => (
                <button
                    key={g}
                    onClick={() => onGenreFilterChange(genreFilter === g ? '' : g)}
                    className={`${btnBase} ${genreFilter === g ? btnActive : btnInactive}`}
                >
                    {g}
                </button>
            ))}
        </div>
    );
}
