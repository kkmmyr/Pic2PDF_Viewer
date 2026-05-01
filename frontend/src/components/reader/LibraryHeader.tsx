import type { LibrarySource, SortOrder } from '../../types';
import type { GroupMode } from '../../hooks/useLibraryGrouping';
import { LibraryNavBar } from './LibraryNavBar';
import { LibraryFilterBar } from './LibraryFilterBar';
import { LibraryBulkActionBar } from './LibraryBulkActionBar';
import type { LibraryBreadcrumb } from './LibraryNavBar';
export type { LibraryBreadcrumb };

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
    groupMode: GroupMode;
    breadcrumbs: LibraryBreadcrumb[];
    showHidden: boolean;
    onUpClick: () => void;
    onSourceChange: (source: LibrarySource) => void;
    onToggleSelectionMode: () => void;
    onBulkSetAuthor: () => void;
    onBulkSetTag: () => void;
    onBulkSetSeries: () => void;
    bulkSeriesDisabled?: boolean;
    onBulkSetGenre: () => void;
    onBulkToggleHidden: () => void;
    onBulkDelete: () => void;
    onRegenThumbnailBulk: () => void;
    onMergePdfs: () => void;
    onSortChange: (order: SortOrder) => void;
    onSearchChange: (text: string) => void;
    onAuthorFilterChange: (author: string) => void;
    onTagFilterChange: (tag: string) => void;
    onGroupModeChange: (mode: GroupMode) => void;
    onToggleShowHidden: () => void;
    showUnreadOnly: boolean;
    onToggleUnreadOnly: () => void;
    onMetaRefresh: () => void;
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
    onBulkSetAuthor,
    onBulkSetTag,
    onBulkSetSeries,
    bulkSeriesDisabled,
    onBulkSetGenre,
    onBulkToggleHidden,
    onBulkDelete,
    onRegenThumbnailBulk,
    onMergePdfs,
    onSortChange,
    onSearchChange,
    onAuthorFilterChange,
    onTagFilterChange,
    onGroupModeChange,
    onToggleShowHidden,
    showUnreadOnly,
    onToggleUnreadOnly,
    onMetaRefresh,
}: LibraryHeaderProps) {
    return (
        <div className="sticky top-0 border-b border-gray-200 dark:border-gray-700 bg-white/90 dark:bg-gray-900/90 backdrop-blur-sm shrink-0 z-header">
            <LibraryNavBar
                currentPath={currentPath}
                currentSource={currentSource}
                breadcrumbs={breadcrumbs}
                onUpClick={onUpClick}
                onSourceChange={onSourceChange}
            />
            <LibraryFilterBar
                searchText={searchText}
                authorFilter={authorFilter}
                tagFilter={tagFilter}
                allAuthors={allAuthors}
                allTags={allTags}
                groupMode={groupMode}
                showUnreadOnly={showUnreadOnly}
                showHidden={showHidden}
                sortOrder={sortOrder}
                currentSource={currentSource}
                hideAuthorSelect={breadcrumbs.length > 0}
                isSelectionMode={isSelectionMode}
                onSearchChange={onSearchChange}
                onAuthorFilterChange={onAuthorFilterChange}
                onTagFilterChange={onTagFilterChange}
                onGroupModeChange={onGroupModeChange}
                onToggleUnreadOnly={onToggleUnreadOnly}
                onToggleShowHidden={onToggleShowHidden}
                onSortChange={onSortChange}
                onMetaRefresh={onMetaRefresh}
                onToggleSelectionMode={onToggleSelectionMode}
            />
            {isSelectionMode && (
                <LibraryBulkActionBar
                    selectedCount={selectedCount}
                    showHidden={showHidden}
                    bulkSeriesDisabled={bulkSeriesDisabled}
                    onBulkSetAuthor={onBulkSetAuthor}
                    onBulkSetTag={onBulkSetTag}
                    onBulkSetSeries={onBulkSetSeries}
                    onBulkSetGenre={onBulkSetGenre}
                    onBulkToggleHidden={onBulkToggleHidden}
                    onBulkDelete={onBulkDelete}
                    onMergePdfs={onMergePdfs}
                    onRegenThumbnailBulk={onRegenThumbnailBulk}
                    onToggleSelectionMode={onToggleSelectionMode}
                />
            )}
        </div>
    );
}
