import { ArrowLeft, ArrowUpDown, Search, User } from 'lucide-react';
import type { LibrarySource, SortOrder } from '../../types';

interface LibraryHeaderProps {
    currentPath: string;
    currentSource: LibrarySource;
    isSelectionMode: boolean;
    selectedCount: number;
    sortOrder: SortOrder;
    searchText: string;
    authorFilter: string;       // '' = フィルターなし
    allAuthors: string[];       // フィルター候補リスト
    onUpClick: () => void;
    onSourceChange: (source: LibrarySource) => void;
    onToggleSelectionMode: () => void;
    onCreateFolder: () => void;
    onMoveSelected: () => void;
    onBulkSetAuthor: () => void;
    onSortChange: (order: SortOrder) => void;
    onSearchChange: (text: string) => void;
    onAuthorFilterChange: (author: string) => void;
}

const SORT_OPTIONS: { value: SortOrder; label: string }[] = [
    { value: 'name_asc',        label: '名前 (A→Z)' },
    { value: 'name_desc',       label: '名前 (Z→A)' },
    { value: 'date_desc',       label: '新しい順' },
    { value: 'date_asc',        label: '古い順' },
    { value: 'favorites_first', label: 'お気に入り優先' },
];

export function LibraryHeader({
    currentPath,
    currentSource,
    isSelectionMode,
    selectedCount,
    sortOrder,
    searchText,
    authorFilter,
    allAuthors,
    onUpClick,
    onSourceChange,
    onToggleSelectionMode,
    onCreateFolder,
    onMoveSelected,
    onBulkSetAuthor,
    onSortChange,
    onSearchChange,
    onAuthorFilterChange,
}: LibraryHeaderProps) {
    return (
        <div className="sticky top-0 border-b border-gray-200 dark:border-gray-700 bg-white/90 dark:bg-gray-900/90 backdrop-blur-sm shrink-0 z-50">
            <div className="h-14 flex items-center px-4 justify-between">
                <div className="flex items-center gap-4">
                    {currentPath && (
                        <button
                            onClick={onUpClick}
                            className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-full"
                        >
                            <ArrowLeft className="w-5 h-5 text-gray-700 dark:text-gray-300" />
                        </button>
                    )}
                    <h1 className="font-semibold truncate text-gray-900 dark:text-gray-100">
                        {currentPath ? currentPath.split('/').pop() : 'Library'}
                    </h1>
                </div>

                <div className="flex items-center gap-3">
                    {/* 通常モード: 検索・作者フィルター・ソート */}
                    {!isSelectionMode && (
                        <>
                            {/* タイトル検索 */}
                            <div className="relative">
                                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400 dark:text-gray-500 pointer-events-none" />
                                <input
                                    type="text"
                                    value={searchText}
                                    onChange={(e) => onSearchChange(e.target.value)}
                                    placeholder="タイトルを検索..."
                                    className="pl-8 pr-3 py-1.5 text-sm border border-gray-200 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-200 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-400 w-44"
                                />
                            </div>

                            {/* 作者フィルター */}
                            {allAuthors.length > 0 && (
                                <div className="flex items-center gap-1 text-sm text-gray-600 dark:text-gray-400">
                                    <User className="w-4 h-4 text-gray-400 dark:text-gray-500 shrink-0" />
                                    <select
                                        value={authorFilter}
                                        onChange={(e) => onAuthorFilterChange(e.target.value)}
                                        className="border border-gray-200 dark:border-gray-600 rounded-md px-2 py-1 text-sm text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-400"
                                    >
                                        <option value="">作者: すべて</option>
                                        {allAuthors.map(a => (
                                            <option key={a} value={a}>{a}</option>
                                        ))}
                                    </select>
                                </div>
                            )}
                        </>
                    )}

                    <div className="flex gap-2 mr-2">
                        {isSelectionMode ? (
                            <>
                                <span className="text-sm font-medium self-center mr-2 text-gray-700 dark:text-gray-300">
                                    {selectedCount} 選択中
                                </span>
                                <button
                                    onClick={onBulkSetAuthor}
                                    disabled={selectedCount === 0}
                                    className="px-3 py-1.5 bg-indigo-600 text-white rounded-md text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed"
                                >
                                    作者を設定
                                </button>
                                <button
                                    onClick={onMoveSelected}
                                    disabled={selectedCount === 0}
                                    className="px-3 py-1.5 bg-blue-600 text-white rounded-md text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
                                >
                                    移動
                                </button>
                                <button
                                    onClick={onToggleSelectionMode}
                                    className="px-3 py-1.5 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-md text-sm font-medium hover:bg-gray-300 dark:hover:bg-gray-600"
                                >
                                    キャンセル
                                </button>
                            </>
                        ) : (
                            <>
                                <button
                                    onClick={onCreateFolder}
                                    className="px-3 py-1.5 bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 rounded-md text-sm font-medium hover:bg-gray-200 dark:hover:bg-gray-700"
                                >
                                    + フォルダ作成
                                </button>
                                <button
                                    onClick={onToggleSelectionMode}
                                    className="px-3 py-1.5 bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 rounded-md text-sm font-medium hover:bg-gray-200 dark:hover:bg-gray-700"
                                >
                                    選択
                                </button>
                            </>
                        )}
                    </div>

                    {!isSelectionMode && (
                        <div className="flex items-center gap-1 text-sm text-gray-600 dark:text-gray-400">
                            <ArrowUpDown className="w-4 h-4 text-gray-400 dark:text-gray-500 shrink-0" />
                            <select
                                value={sortOrder}
                                onChange={(e) => onSortChange(e.target.value as SortOrder)}
                                className="border border-gray-200 dark:border-gray-600 rounded-md px-2 py-1 text-sm text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-400"
                            >
                                {SORT_OPTIONS.map(opt => (
                                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                                ))}
                            </select>
                        </div>
                    )}

                    <div className="flex bg-gray-100 dark:bg-gray-800 rounded-lg p-1">
                        {(['generated', 'kindle', 'novel'] as LibrarySource[]).map((src) => (
                            <button
                                key={src}
                                onClick={() => onSourceChange(src)}
                                className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
                                    currentSource === src
                                        ? 'bg-white dark:bg-gray-700 text-blue-600 dark:text-blue-400 shadow-sm'
                                        : 'text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200'
                                }`}
                            >
                                {src === 'generated' ? 'Main' : src === 'kindle' ? 'Kindle' : 'Novel'}
                            </button>
                        ))}
                    </div>
                </div>
            </div>
        </div>
    );
}
