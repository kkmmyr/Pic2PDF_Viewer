import { Library, BookOpen, Eye, EyeOff } from 'lucide-react';
import type { LibrarySource, ReadState, SortOrder } from '../../types';
import type { GroupMode } from '../../hooks/useLibraryGrouping';
import { HeaderSearchBar } from './HeaderSearchBar';
import { HeaderSortSelect } from './HeaderSortSelect';
import { ToolsMenu } from './ToolsMenu';
import { Button } from '../ui/Button';

type ReadStateFilter = '' | ReadState;

interface LibraryFilterBarProps {
    searchText: string;
    authorFilter: string;
    allAuthors: string[];
    groupMode: GroupMode;
    readStateFilter: ReadStateFilter;
    showHidden: boolean;
    sortOrder: SortOrder;
    currentSource: LibrarySource;
    hideAuthorSelect: boolean;
    isSelectionMode: boolean;
    onSearchChange: (text: string) => void;
    onAuthorFilterChange: (author: string) => void;
    onGroupModeChange: (mode: GroupMode) => void;
    onReadStateFilterChange: (value: ReadStateFilter) => void;
    onToggleShowHidden: () => void;
    onSortChange: (order: SortOrder) => void;
    onMetaRefresh: () => void;
    onToggleSelectionMode: () => void;
}

export function LibraryFilterBar({
    searchText,
    authorFilter,
    allAuthors,
    groupMode,
    readStateFilter,
    showHidden,
    sortOrder,
    currentSource,
    hideAuthorSelect,
    isSelectionMode,
    onSearchChange,
    onAuthorFilterChange,
    onGroupModeChange,
    onReadStateFilterChange,
    onToggleShowHidden,
    onSortChange,
    onMetaRefresh,
    onToggleSelectionMode,
}: LibraryFilterBarProps) {
    return (
        <div className="h-12 flex items-center px-4 gap-3 border-t border-gray-100 dark:border-gray-800">
            <HeaderSearchBar
                searchText={searchText}
                authorFilter={authorFilter}
                allAuthors={allAuthors}
                hideAuthorSelect={hideAuthorSelect}
                onSearchChange={onSearchChange}
                onAuthorFilterChange={onAuthorFilterChange}
            />

            <div className="flex-1" />

            {/* グループ化 select（ネイティブ select、色は中立） */}
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
                    className={`border rounded-md px-2 py-1 text-sm bg-white dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-accent-400 max-w-[140px] truncate ${
                        groupMode !== 'none'
                            ? 'text-accent-700 dark:text-accent-300 border-accent-400 dark:border-accent-600 ring-1 ring-accent-200 dark:ring-accent-800'
                            : 'text-gray-700 dark:text-gray-300 border-gray-200 dark:border-gray-600'
                    }`}
                >
                    <option value="none">グループ化なし</option>
                    <option value="series">シリーズで</option>
                    <option value="author">作者で</option>
                    <option value="author-then-series">作者 → シリーズで</option>
                </select>
            </div>

            {/* 読書状態フィルタ。空文字 = 全件表示 / unread = 未読 / reading = 読書中 / done = 読了。 */}
            <div className="flex items-center gap-1 text-sm text-gray-600 dark:text-gray-400">
                <BookOpen className="w-4 h-4 text-gray-400 dark:text-gray-500 shrink-0" />
                <select
                    value={readStateFilter}
                    onChange={(e) => onReadStateFilterChange(e.target.value as ReadStateFilter)}
                    title="読書状態で絞り込む"
                    className={`border rounded-md px-2 py-1 text-sm bg-white dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-accent-400 ${
                        readStateFilter
                            ? 'text-accent-700 dark:text-accent-300 border-accent-400 dark:border-accent-600 ring-1 ring-accent-200 dark:ring-accent-800'
                            : 'text-gray-700 dark:text-gray-300 border-gray-200 dark:border-gray-600'
                    }`}
                >
                    <option value="">読書状態すべて</option>
                    <option value="unread">未読のみ</option>
                    <option value="reading">読書中のみ</option>
                    <option value="done">読了のみ</option>
                </select>
            </div>

            <Button
                variant="secondary"
                active={showHidden}
                onClick={onToggleShowHidden}
                title={showHidden ? '通常モードに戻る' : '非表示書籍を表示する（ゴミ箱）'}
            >
                {showHidden ? <Eye className="w-4 h-4" /> : <EyeOff className="w-4 h-4" />}
                {showHidden ? '通常表示' : '非表示を表示'}
            </Button>

            <HeaderSortSelect sortOrder={sortOrder} onSortChange={onSortChange} />

            <ToolsMenu source={currentSource} onComplete={onMetaRefresh} />

            {!isSelectionMode && (
                <Button variant="secondary" onClick={onToggleSelectionMode}>
                    選択
                </Button>
            )}
        </div>
    );
}
