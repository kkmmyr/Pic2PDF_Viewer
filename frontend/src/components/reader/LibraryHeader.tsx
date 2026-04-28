import { ArrowLeft, ImageIcon, Merge, Tag, Library, EyeOff, Eye, ChevronRight, Home, User } from 'lucide-react';
import type { LibrarySource, SortOrder } from '../../types';
import type { GroupMode } from '../../hooks/useLibraryGrouping';
import { HeaderSearchBar } from './HeaderSearchBar';
import { HeaderSortSelect } from './HeaderSortSelect';
import { SourceSelector } from './SourceSelector';

export interface LibraryBreadcrumb {
    kind: 'home' | 'author' | 'series';
    label: string;
    /** 指定なしならクリック不可（現在地） */
    onClick?: () => void;
}

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
    /** ライブラリの集約モード（none / series / author / author-then-series） */
    groupMode: GroupMode;
    /** ドリルダウン中のパンくず（空配列なら非表示）。先頭から順に並び、最後の要素は現在地 */
    breadcrumbs: LibraryBreadcrumb[];
    /** 非表示書籍を表示するモード（ゴミ箱モード） */
    showHidden: boolean;
    onUpClick: () => void;
    onSourceChange: (source: LibrarySource) => void;
    onToggleSelectionMode: () => void;
    onCreateFolder: () => void;
    onMoveSelected: () => void;
    onBulkSetAuthor: () => void;
    onBulkSetTag: () => void;
    onBulkSetSeries: () => void;
    onBulkToggleHidden: () => void;
    onRegenThumbnailBulk: () => void;
    onMergePdfs: () => void;
    onSortChange: (order: SortOrder) => void;
    onSearchChange: (text: string) => void;
    onAuthorFilterChange: (author: string) => void;
    onTagFilterChange: (tag: string) => void;
    onGroupModeChange: (mode: GroupMode) => void;
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
    groupMode,
    breadcrumbs,
    showHidden,
    onUpClick,
    onSourceChange,
    onToggleSelectionMode,
    onCreateFolder,
    onMoveSelected,
    onBulkSetAuthor,
    onBulkSetTag,
    onBulkSetSeries,
    onBulkToggleHidden,
    onRegenThumbnailBulk,
    onMergePdfs,
    onSortChange,
    onSearchChange,
    onAuthorFilterChange,
    onTagFilterChange,
    onGroupModeChange,
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
                            // パンくず表示中は作者 select を隠して操作をパンくずに集約する
                            hideAuthorSelect={breadcrumbs.length > 0}
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
                                    onClick={onBulkSetSeries}
                                    disabled={selectedCount === 0}
                                    title="選択した書籍をシリーズに一括登録（選択順に採番）"
                                    className="px-3 py-1.5 bg-purple-600 text-white rounded-md text-sm font-medium hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5"
                                >
                                    <Library className="w-4 h-4" />
                                    シリーズに登録
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
                        <div className="flex items-center gap-1 text-sm text-gray-600 dark:text-gray-400">
                            <Library className="w-4 h-4 text-gray-400 dark:text-gray-500 shrink-0" />
                            <select
                                value={groupMode}
                                onChange={(e) => onGroupModeChange(e.target.value as GroupMode)}
                                title="ライブラリの集約表示"
                                /*
                                 * select 自身の背景は常に bg-white / dark:bg-gray-800 に固定する。
                                 * Chromium では <option> の背景色が <select> の bg を継承し、
                                 * かつ CSS で <option> 個別に上書きできないため、<select> 側で
                                 * 紫背景にすると <option> がダークモードで読めなくなる。
                                 * 紫強調は border + ring + 文字色で表現する。
                                 */
                                className={`border rounded-md px-2 py-1 text-sm bg-white dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-purple-400 max-w-[140px] truncate ${
                                    groupMode !== 'none'
                                        ? 'text-purple-700 dark:text-purple-300 border-purple-400 dark:border-purple-600 ring-1 ring-purple-200 dark:ring-purple-800'
                                        : 'text-gray-700 dark:text-gray-300 border-gray-200 dark:border-gray-600'
                                }`}
                            >
                                <option value="none">グループ化なし</option>
                                <option value="series">シリーズで</option>
                                <option value="author">作者で</option>
                                <option value="author-then-series">作者 → シリーズで</option>
                            </select>
                        </div>
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

            {/* ドリルダウン中のパンくず（フィルター適用時のみ表示） */}
            {!isSelectionMode && breadcrumbs.length > 0 && (
                <div className="px-4 py-1.5 flex items-center gap-1.5 text-sm text-gray-700 dark:text-gray-300 border-t border-gray-100 dark:border-gray-800 bg-gray-50/60 dark:bg-gray-900/40">
                    {breadcrumbs.map((crumb, i) => {
                        const isLast = i === breadcrumbs.length - 1;
                        const Icon = crumb.kind === 'home' ? Home : crumb.kind === 'author' ? User : Library;
                        const labelEl = (
                            <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded ${
                                isLast
                                    ? 'bg-purple-100 dark:bg-purple-900/40 text-purple-700 dark:text-purple-300 font-medium'
                                    : crumb.onClick
                                        ? 'hover:bg-gray-200 dark:hover:bg-gray-800 cursor-pointer'
                                        : ''
                            }`}>
                                <Icon className="w-3.5 h-3.5" />
                                <span className="truncate max-w-[180px]">{crumb.label}</span>
                            </span>
                        );
                        return (
                            <span key={`${crumb.kind}-${i}`} className="inline-flex items-center gap-1.5">
                                {i > 0 && <ChevronRight className="w-3.5 h-3.5 text-gray-400 dark:text-gray-500 shrink-0" />}
                                {crumb.onClick && !isLast
                                    ? <button onClick={crumb.onClick}>{labelEl}</button>
                                    : labelEl}
                            </span>
                        );
                    })}
                </div>
            )}
        </div>
    );
}
