import { useState } from 'react';
import { Eye, EyeOff, ListChecks, SlidersHorizontal, X } from 'lucide-react';
import type { LibrarySource, ReadState, SortOrder } from '@/types';
import type { GroupMode } from '@/hooks/library/useLibraryGrouping';
import { HeaderSearchBar } from '@/components/library/HeaderSearchBar';
import { HeaderSortSelect } from '@/components/library/HeaderSortSelect';
import { LibraryDetailFilters } from '@/components/library/LibraryDetailFilters';
import { LibraryFilterDialog } from '@/components/library/LibraryFilterDialog';
import { ToolsMenu } from '@/components/library/ToolsMenu';
import { Button } from '@/components/ui/button';

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
    isLoading: boolean;
    activeFilterCount: number;
    resultBookCount: number;
    totalBookCount: number;
    onSearchChange: (text: string) => void;
    onAuthorFilterChange: (author: string) => void;
    onGroupModeChange: (mode: GroupMode) => void;
    onReadStateFilterChange: (value: ReadStateFilter) => void;
    onToggleShowHidden: () => void;
    onSortChange: (order: SortOrder) => void;
    onToggleSelectionMode: () => void;
    onClearFilters: () => void;
}

function ResultSummary({
    isLoading,
    activeFilterCount,
    resultBookCount,
    totalBookCount,
}: Pick<
    LibraryFilterBarProps,
    'isLoading' | 'activeFilterCount' | 'resultBookCount' | 'totalBookCount'
>) {
    return (
        <div
            className="flex min-w-0 items-center gap-2 text-xs text-gray-600 dark:text-gray-300"
            aria-live="polite"
        >
            <span className="whitespace-nowrap font-medium">
                {isLoading ? '読み込み中…' : `${resultBookCount} / ${totalBookCount}冊`}
            </span>
            {activeFilterCount > 0 && (
                <span className="whitespace-nowrap rounded-full bg-primary-100 px-2 py-1 font-medium text-primary-700 dark:bg-primary-900/50 dark:text-primary-200">
                    {activeFilterCount}条件
                </span>
            )}
        </div>
    );
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
    isLoading,
    activeFilterCount,
    resultBookCount,
    totalBookCount,
    onSearchChange,
    onAuthorFilterChange,
    onGroupModeChange,
    onReadStateFilterChange,
    onToggleShowHidden,
    onSortChange,
    onToggleSelectionMode,
    onClearFilters,
}: LibraryFilterBarProps) {
    const [filterDialogOpen, setFilterDialogOpen] = useState(false);

    return (
        <div className="border-t border-gray-100 dark:border-gray-800">
            <div className="space-y-3 px-4 py-3 lg:hidden" data-testid="mobile-library-controls">
                <HeaderSearchBar
                    searchText={searchText}
                    onSearchChange={onSearchChange}
                    className="w-full"
                />
                <div className="flex min-w-0 items-center gap-2">
                    <Button
                        variant="secondary"
                        active={activeFilterCount > 0}
                        className="relative min-h-11 shrink-0 px-3"
                        aria-label={
                            activeFilterCount > 0
                                ? `絞り込み、${activeFilterCount}件の条件を適用中`
                                : '絞り込み'
                        }
                        onClick={() => setFilterDialogOpen(true)}
                    >
                        <SlidersHorizontal className="h-4 w-4" />
                        絞り込み
                        {activeFilterCount > 0 && (
                            <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-white px-1 text-[11px] font-bold text-gray-800 dark:bg-gray-100">
                                {activeFilterCount}
                            </span>
                        )}
                    </Button>
                    <HeaderSortSelect
                        sortOrder={sortOrder}
                        onSortChange={onSortChange}
                        compact
                        className="min-w-0 flex-1"
                    />
                    <ToolsMenu source={currentSource} />
                </div>
                <div className="flex min-h-6 items-center justify-between gap-3">
                    <ResultSummary
                        isLoading={isLoading}
                        activeFilterCount={activeFilterCount}
                        resultBookCount={resultBookCount}
                        totalBookCount={totalBookCount}
                    />
                    {activeFilterCount > 0 && (
                        <button
                            type="button"
                            onClick={onClearFilters}
                            className="inline-flex min-h-8 shrink-0 items-center gap-1 rounded-md px-2 text-xs font-medium text-gray-600 hover:bg-gray-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 dark:text-gray-300 dark:hover:bg-gray-800"
                        >
                            <X className="h-3.5 w-3.5" />
                            条件解除
                        </button>
                    )}
                </div>
            </div>

            <div
                className="hidden flex-wrap items-center gap-3 px-4 py-2.5 lg:flex"
                data-testid="desktop-library-controls"
            >
                <HeaderSearchBar
                    searchText={searchText}
                    onSearchChange={onSearchChange}
                    className="min-w-56 flex-1 xl:max-w-xs"
                />
                <LibraryDetailFilters
                    authorFilter={authorFilter}
                    allAuthors={allAuthors}
                    groupMode={groupMode}
                    readStateFilter={readStateFilter}
                    hideAuthorSelect={hideAuthorSelect}
                    layout="inline"
                    onAuthorFilterChange={onAuthorFilterChange}
                    onGroupModeChange={onGroupModeChange}
                    onReadStateFilterChange={onReadStateFilterChange}
                />
                <HeaderSortSelect sortOrder={sortOrder} onSortChange={onSortChange} />
                <ResultSummary
                    isLoading={isLoading}
                    activeFilterCount={activeFilterCount}
                    resultBookCount={resultBookCount}
                    totalBookCount={totalBookCount}
                />

                <div className="ml-auto flex items-center gap-2 border-l border-gray-200 pl-3 dark:border-gray-700">
                    <Button
                        variant="secondary"
                        active={showHidden}
                        className="min-h-9 px-3"
                        aria-pressed={showHidden}
                        onClick={onToggleShowHidden}
                        title={showHidden ? '通常の書籍を表示' : '非表示の書籍を表示'}
                    >
                        {showHidden ? <Eye className="h-4 w-4" /> : <EyeOff className="h-4 w-4" />}
                        {showHidden ? '通常表示' : '非表示一覧'}
                    </Button>
                    {!isSelectionMode && (
                        <Button
                            variant="ghost"
                            className="min-h-9 px-3"
                            onClick={onToggleSelectionMode}
                        >
                            <ListChecks className="h-4 w-4" />
                            選択
                        </Button>
                    )}
                    <ToolsMenu source={currentSource} />
                </div>
            </div>

            <LibraryFilterDialog
                open={filterDialogOpen}
                activeFilterCount={activeFilterCount}
                authorFilter={authorFilter}
                allAuthors={allAuthors}
                groupMode={groupMode}
                readStateFilter={readStateFilter}
                showHidden={showHidden}
                currentSource={currentSource}
                hideAuthorSelect={hideAuthorSelect}
                isSelectionMode={isSelectionMode}
                onAuthorFilterChange={onAuthorFilterChange}
                onGroupModeChange={onGroupModeChange}
                onReadStateFilterChange={onReadStateFilterChange}
                onToggleShowHidden={onToggleShowHidden}
                onToggleSelectionMode={onToggleSelectionMode}
                onClearFilters={onClearFilters}
                onClose={() => setFilterDialogOpen(false)}
            />
        </div>
    );
}
