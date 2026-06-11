import { useLibraryPanelContext } from '@/contexts/LibraryPanelContext';
import { LibraryNavBar } from './LibraryNavBar';
import { LibraryFilterBar } from './LibraryFilterBar';
import { LibraryBulkActionBar } from './LibraryBulkActionBar';

export function LibraryHeader() {
    const {
        currentPath,
        currentSource,
        isSelectionMode,
        selectedItems,
        sortOrder,
        setSortOrder,
        searchText,
        setSearchText,
        authorFilter,
        setAuthorFilter,
        allAuthors,
        groupMode,
        handleGroupModeChange,
        breadcrumbs,
        showHidden,
        toggleShowHidden,
        readStateFilter,
        setReadStateFilter,
        toggleSelectionMode,
        dialogs,
        bulkActions,
        isMixedAuthors,
        refreshMeta,
        onUpClick,
    } = useLibraryPanelContext();

    return (
        <div className="sticky top-0 border-b border-gray-200 dark:border-gray-700 bg-white/90 dark:bg-gray-900/90 backdrop-blur-sm shrink-0 z-header">
            <LibraryNavBar
                currentPath={currentPath}
                breadcrumbs={breadcrumbs}
                onUpClick={onUpClick}
            />
            <LibraryFilterBar
                searchText={searchText}
                authorFilter={authorFilter}
                allAuthors={allAuthors}
                groupMode={groupMode}
                readStateFilter={readStateFilter}
                showHidden={showHidden}
                sortOrder={sortOrder}
                currentSource={currentSource}
                hideAuthorSelect={breadcrumbs.length > 0}
                isSelectionMode={isSelectionMode}
                onSearchChange={setSearchText}
                onAuthorFilterChange={setAuthorFilter}
                onGroupModeChange={handleGroupModeChange}
                onReadStateFilterChange={setReadStateFilter}
                onToggleShowHidden={toggleShowHidden}
                onSortChange={setSortOrder}
                onMetaRefresh={refreshMeta}
                onToggleSelectionMode={toggleSelectionMode}
            />
            {isSelectionMode && (
                <LibraryBulkActionBar
                    selectedCount={selectedItems.size}
                    showHidden={showHidden}
                    bulkSeriesDisabled={isMixedAuthors}
                    onBulkSetAuthor={() => dialogs.open('bulkAuthor')}
                    onBulkSetSeries={() => dialogs.open('bulkSeries')}
                    onBulkSetGenre={() => dialogs.open('bulkGenre')}
                    onBulkToggleHidden={bulkActions.handleBulkToggleHidden}
                    onBulkDelete={bulkActions.handleBulkDelete}
                    onMergePdfs={() => dialogs.open('merge')}
                    onRegenThumbnailBulk={bulkActions.handleRegenThumbnailBulk}
                    onToggleSelectionMode={toggleSelectionMode}
                />
            )}
        </div>
    );
}
