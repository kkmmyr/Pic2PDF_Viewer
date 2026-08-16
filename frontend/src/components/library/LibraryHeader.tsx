import { useState } from 'react';
import { useLibraryPanelContext } from '@/contexts/LibraryPanelContext';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import { LibraryNavBar } from './LibraryNavBar';
import { LibraryFilterBar } from './LibraryFilterBar';
import { LibraryBulkActionBar } from './LibraryBulkActionBar';

export function LibraryHeader() {
    const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
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
        isPdfsLoading,
        activeFilterCount,
        resultBookCount,
        totalBookCount,
        clearLibraryFilters,
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
                isLoading={isPdfsLoading}
                activeFilterCount={activeFilterCount}
                resultBookCount={resultBookCount}
                totalBookCount={totalBookCount}
                onSearchChange={setSearchText}
                onAuthorFilterChange={setAuthorFilter}
                onGroupModeChange={handleGroupModeChange}
                onReadStateFilterChange={setReadStateFilter}
                onToggleShowHidden={toggleShowHidden}
                onSortChange={setSortOrder}
                onMetaRefresh={refreshMeta}
                onToggleSelectionMode={toggleSelectionMode}
                onClearFilters={clearLibraryFilters}
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
                    onBulkDelete={() => setDeleteConfirmOpen(true)}
                    onMergePdfs={() => dialogs.open('merge')}
                    onRegenThumbnailBulk={bulkActions.handleRegenThumbnailBulk}
                    onToggleSelectionMode={toggleSelectionMode}
                />
            )}
            <ConfirmDialog
                open={deleteConfirmOpen}
                title="選択した書籍を完全に削除しますか？"
                message={`選択した ${selectedItems.size} 件をディスクから完全に削除します。\nこの操作は元に戻せません。`}
                confirmLabel="完全に削除"
                danger
                onConfirm={() => {
                    setDeleteConfirmOpen(false);
                    void bulkActions.handleBulkDelete();
                }}
                onCancel={() => setDeleteConfirmOpen(false)}
            />
        </div>
    );
}
