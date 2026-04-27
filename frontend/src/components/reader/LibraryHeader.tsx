import { ArrowLeft, ImageIcon, Merge } from 'lucide-react';
import type { LibrarySource, SortOrder } from '../../types';
import { HeaderSearchBar } from './HeaderSearchBar';
import { HeaderSortSelect } from './HeaderSortSelect';
import { SourceSelector } from './SourceSelector';

interface LibraryHeaderProps {
    currentPath: string;
    currentSource: LibrarySource;
    isSelectionMode: boolean;
    selectedCount: number;
    sortOrder: SortOrder;
    searchText: string;
    authorFilter: string;
    allAuthors: string[];
    onUpClick: () => void;
    onSourceChange: (source: LibrarySource) => void;
    onToggleSelectionMode: () => void;
    onCreateFolder: () => void;
    onMoveSelected: () => void;
    onBulkSetAuthor: () => void;
    onRegenThumbnailBulk: () => void;
    onMergePdfs: () => void;
    onSortChange: (order: SortOrder) => void;
    onSearchChange: (text: string) => void;
    onAuthorFilterChange: (author: string) => void;
}

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
    onRegenThumbnailBulk,
    onMergePdfs,
    onSortChange,
    onSearchChange,
    onAuthorFilterChange,
}: LibraryHeaderProps) {
    return (
        <div className="sticky top-0 border-b border-gray-200 dark:border-gray-700 bg-white/90 dark:bg-gray-900/90 backdrop-blur-sm shrink-0 z-header">
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
                    {!isSelectionMode && (
                        <HeaderSearchBar
                            searchText={searchText}
                            authorFilter={authorFilter}
                            allAuthors={allAuthors}
                            onSearchChange={onSearchChange}
                            onAuthorFilterChange={onAuthorFilterChange}
                        />
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
                                    onClick={onMergePdfs}
                                    disabled={selectedCount < 2}
                                    title="選択した書籍を1つのPDFに結合"
                                    className="px-3 py-1.5 bg-emerald-600 text-white rounded-md text-sm font-medium hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5"
                                >
                                    <Merge className="w-4 h-4" />
                                    結合
                                </button>
                                <button
                                    onClick={onRegenThumbnailBulk}
                                    disabled={selectedCount === 0}
                                    title="選択した書籍のサムネイルを再生成"
                                    className="px-3 py-1.5 bg-amber-600 text-white rounded-md text-sm font-medium hover:bg-amber-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5"
                                >
                                    <ImageIcon className="w-4 h-4" />
                                    サムネイル再生成
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
                        <HeaderSortSelect sortOrder={sortOrder} onSortChange={onSortChange} />
                    )}

                    <SourceSelector currentSource={currentSource} onSourceChange={onSourceChange} />
                </div>
            </div>
        </div>
    );
}
