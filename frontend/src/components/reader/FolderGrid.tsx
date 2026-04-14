import { Folder, CheckSquare, Square } from 'lucide-react';

interface FolderGridProps {
    directories: string[];
    onFolderClick: (dirName: string) => void;
    isSelectionMode?: boolean;
    selectedItems?: Set<string>;
    onToggleSelect?: (name: string) => void;
}

export function FolderGrid({
    directories,
    onFolderClick,
    isSelectionMode = false,
    selectedItems = new Set(),
    onToggleSelect
}: FolderGridProps) {
    if (directories.length === 0) return null;

    return (
        <div className="mb-8">
            <h2 className="text-lg font-semibold mb-4 text-gray-700 dark:text-gray-300">Folders</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
                {directories.map((dir) => (
                    <div
                        key={dir}
                        className={`bg-white dark:bg-gray-800 rounded-lg shadow-md p-4 flex flex-col items-center justify-center cursor-pointer hover:shadow-lg transition-shadow border-2 ${
                            isSelectionMode && selectedItems.has(dir)
                                ? 'border-blue-500'
                                : 'border-transparent'
                        }`}
                        onClick={() => {
                            if (isSelectionMode && onToggleSelect) {
                                onToggleSelect(dir);
                            } else {
                                onFolderClick(dir);
                            }
                        }}
                    >
                        <div className="relative">
                            <Folder className="w-12 h-12 text-yellow-500 fill-yellow-500 mb-2" />
                            {isSelectionMode && (
                                <div className="absolute -top-2 -right-2 bg-white dark:bg-gray-800 rounded-full">
                                    {selectedItems.has(dir) ? (
                                        <CheckSquare className="w-5 h-5 text-blue-500 fill-white" />
                                    ) : (
                                        <Square className="w-5 h-5 text-gray-400 fill-white" />
                                    )}
                                </div>
                            )}
                        </div>
                        <span className="text-sm font-medium text-gray-700 dark:text-gray-300 text-center break-words w-full line-clamp-2">
                            {dir}
                        </span>
                    </div>
                ))}
            </div>
        </div>
    );
}
