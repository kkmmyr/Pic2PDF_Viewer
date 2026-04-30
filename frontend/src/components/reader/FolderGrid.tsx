import { Folder, Check, Pencil } from 'lucide-react';

interface FolderGridProps {
    directories: string[];
    onFolderClick: (dirName: string) => void;
    isSelectionMode?: boolean;
    selectedItems?: Set<string>;
    onToggleSelect?: (name: string) => void;
    onRename?: (name: string) => void;
    /** フォルダ直下の未読書籍数を返す関数。0 なら非表示 */
    getUnreadCount?: (dirName: string) => number;
}

export function FolderGrid({
    directories,
    onFolderClick,
    isSelectionMode = false,
    selectedItems = new Set(),
    onToggleSelect,
    onRename,
    getUnreadCount,
}: FolderGridProps) {
    if (directories.length === 0) return null;

    return (
        <div className="mb-8">
            <h2 className="text-lg font-semibold mb-4 text-gray-700 dark:text-gray-300">Folders</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
                {directories.map((dir) => {
                    const isSelected = isSelectionMode && selectedItems.has(dir);
                    const unreadCount = getUnreadCount?.(dir) ?? 0;
                    return (
                    <div
                        key={dir}
                        className={`rounded-lg shadow-md p-4 flex flex-col items-center justify-center cursor-pointer hover:shadow-lg transition-shadow border-2 ${
                            isSelected
                                ? 'border-amber-400 bg-amber-50 dark:bg-amber-900/20'
                                : 'border-transparent bg-white dark:bg-gray-800'
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
                                <div className="absolute -top-2 -right-2">
                                    {isSelected ? (
                                        <div className="w-5 h-5 rounded-full bg-amber-500 flex items-center justify-center shadow-md ring-2 ring-white dark:ring-gray-800">
                                            <Check className="w-3 h-3 text-white" strokeWidth={3} />
                                        </div>
                                    ) : (
                                        <div className="w-5 h-5 rounded-full bg-white/90 dark:bg-gray-800/90 border-2 border-gray-400 dark:border-gray-500 shadow-sm" />
                                    )}
                                </div>
                            )}
                            {!isSelectionMode && unreadCount > 0 && (
                                <div className="absolute -top-2 -right-2 min-w-[1.25rem] h-5 rounded-full bg-sky-500 text-white text-xs font-semibold flex items-center justify-center px-1 shadow">
                                    {unreadCount}
                                </div>
                            )}
                        </div>
                        <div className="flex items-center justify-center gap-1 w-full">
                            <span className="text-sm font-medium text-gray-700 dark:text-gray-300 text-center break-words line-clamp-2 flex-1">
                                {dir}
                            </span>
                            {!isSelectionMode && onRename && (
                                <button
                                    onClick={(e) => { e.stopPropagation(); onRename(dir); }}
                                    className="p-0.5 rounded hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-300 dark:text-gray-600 hover:text-gray-500 dark:hover:text-gray-400 transition-colors shrink-0"
                                    title="名前を変更"
                                >
                                    <Pencil className="w-3 h-3" />
                                </button>
                            )}
                        </div>
                    </div>
                    );
                })}
            </div>
        </div>
    );
}
