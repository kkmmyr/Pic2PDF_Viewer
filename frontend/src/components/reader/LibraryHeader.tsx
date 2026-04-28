import { ArrowLeft, ImageIcon, Merge, Tag, Library, EyeOff, Eye } from 'lucide-react';
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
    tagFilter: string;
    allAuthors: string[];
    allTags: string[];
    /** シリーズグループ化トグルの状態 */
    isGroupedBySeries: boolean;
    /** 非表示書籍を表示するモード（ゴミ箱モード） */
    showHidden: boolean;
    onUpClick: () => void;
    onSourceChange: (source: LibrarySource) => void;
    onToggleSelectionMode: () => void;
    onCreateFolder: () => void;
    onMoveSelected: () => void;
    onBulkSetAuthor: () => void;
    onBulkSetTag: () => void;
    onBulkToggleHidden: () => void;
    onRegenThumbnailBulk: () => void;
    onMergePdfs: () => void;
    onSortChange: (order: SortOrder) => void;
    onSearchChange: (text: string) => void;
    onAuthorFilterChange: (author: string) => void;
    onTagFilterChange: (tag: string) => void;
    onToggleGroupBySeries: () => void;
    onToggleShowHidden: () => void;
}

export function LibraryHeader({
    currentPath,
    currentSource,
    isSelectionMode,
    selectedCount,
    sortOrder,
    searchText,
    authorFilter,
    tagFilter,
    allAuthors,
    allTags,
    isGroupedBySeries,
    showHidden,
    onUpClick,
    onSourceChange,
    onToggleSelectionMode,
    onCreateFolder,
    onMoveSelected,
    onBulkSetAuthor,
    onBulkSetTag,
    onBulkToggleHidden,
    onRegenThumbnailBulk,
    onMergePdfs,
    onSortChange,
    onSearchChange,
    onAuthorFilterChange,
    onTagFilterChange,
    onToggleGroupBySeries,
    onToggleShowHidden,
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
                            tagFilter={tagFilter}
                            allAuthors={allAuthors}
                            allTags={allTags}
                            onSearchChange={onSearchChange}
                            onAuthorFilterChange={onAuthorFilterChange}
                            onTagFilterChange={onTagFilterChange}
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
                                    onClick={onBulkSetTag}
                                    disabled={selectedCount === 0}
                                    title="選択した書籍のタグを一括設定"
                                    className="px-3 py-1.5 bg-emerald-700 text-white rounded-md text-sm font-medium hover:bg-emerald-800 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5"
                                >
                                    <Tag className="w-4 h-4" />
                                    タグを設定
                                </button>
                                <button
                                    onClick={onBulkToggleHidden}
                                    disabled={selectedCount === 0}
                                    title={showHidden ? '選択した書籍を再表示' : '選択した書籍を非表示'}
                                    className="px-3 py-1.5 bg-gray-600 text-white rounded-md text-sm font-medium hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5"
                                >
                                    {showHidden ? <Eye className="w-4 h-4" /> : <EyeOff className="w-4 h-4" />}
                                    {showHidden ? 'まとめて再表示' : 'まとめて非表示'}
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
                        <button
                            onClick={onToggleGroupBySeries}
                            title={isGroupedBySeries ? 'シリーズグループ化をオフにする' : 'シリーズでグループ化'}
                            className={`px-3 py-1.5 rounded-md text-sm font-medium flex items-center gap-1.5 transition-colors ${
                                isGroupedBySeries
                                    ? 'bg-purple-100 dark:bg-purple-900/40 text-purple-700 dark:text-purple-300 border border-purple-200 dark:border-purple-700'
                                    : 'bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700'
                            }`}
                        >
                            <Library className="w-4 h-4" />
                            シリーズ
                        </button>
                    )}

                    {!isSelectionMode && (
                        <button
                            onClick={onToggleShowHidden}
                            title={showHidden ? '通常モードに戻る' : '非表示書籍を表示する（ゴミ箱）'}
                            className={`px-3 py-1.5 rounded-md text-sm font-medium flex items-center gap-1.5 transition-colors ${
                                showHidden
                                    ? 'bg-gray-700 text-white hover:bg-gray-800'
                                    : 'bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700'
                            }`}
                        >
                            {showHidden ? <Eye className="w-4 h-4" /> : <EyeOff className="w-4 h-4" />}
                            {showHidden ? '通常表示' : '非表示を表示'}
                        </button>
                    )}

                    {!isSelectionMode && (
                        <HeaderSortSelect sortOrder={sortOrder} onSortChange={onSortChange} />
                    )}

                    <SourceSelector currentSource={currentSource} onSourceChange={onSourceChange} />
                </div>
            </div>
        </div>
    );
}
