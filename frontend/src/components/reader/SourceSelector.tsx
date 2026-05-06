import type { LibrarySource } from '../../types';

interface SourceSelectorProps {
    currentSource: LibrarySource;
    onSourceChange: (source: LibrarySource) => void;
}

const SOURCES: { value: LibrarySource; label: string }[] = [
    { value: 'generated', label: 'Main' },
    { value: 'kindle', label: 'Kindle' },
    { value: 'novel', label: 'Novel' },
];

export function SourceSelector({ currentSource, onSourceChange }: SourceSelectorProps) {
    return (
        <div className="flex bg-gray-100 dark:bg-gray-800 rounded-lg p-1">
            {SOURCES.map(({ value, label }) => (
                <button
                    key={value}
                    onClick={() => onSourceChange(value)}
                    className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
                        currentSource === value
                            ? 'bg-white dark:bg-gray-700 text-blue-600 dark:text-blue-400 shadow-sm'
                            : 'text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200'
                    }`}
                >
                    {label}
                </button>
            ))}
        </div>
    );
}
