import { LibraryHeader, PdfGrid, ToastContainer, GenreFilterBar } from '../reader';
import { LibraryDialogs } from './LibraryDialogs';
import { SeriesEditDialog } from './SeriesEditDialog';
import { useLibraryPanel } from '../../hooks/useLibraryPanel';

interface LibraryPanelProps {
    onPdfClick: (name: string) => void;
    onUpClick: () => void;
}

export function LibraryPanel({ onPdfClick, onUpClick }: LibraryPanelProps) {
    const {
        currentPath,
        currentSource,
        isSelectionMode,
        selectedItems,
        renameTarget,
        openRenameDialog,
        closeRenameDialog,
        handleRename,
        toggleSelectionMode,
        searchText,
        setSearchText,
        dialogs,
        authorFilter,
        seriesFilter,
        setAuthorFilter,
        setSeriesFilter,
        sortOrder,
        setSortOrder,
        groupMode,
        showHidden,
        toggleShowHidden,
        readStateFilter,
        setReadStateFilter,
        genreFilter,
        setGenreFilter,
        handleGroupModeChange,
        handlePdfClick,
        handleRegenThumb,
        handleTogglePin,
        handleToggleSelect,
        getAuthors,
        getSeries,
        getReadState,
        allAuthors,
        refreshMeta,
        genres,
        addGenre,
        removeGenre,
        reorderGenres,
        toasts,
        dismissToast,
        grouped,
        displayPdfs,
        breadcrumbs,
        contextualFavorites,
        bulkActions,
        seriesEdit,
        seriesEditFilteredSeries,
        bulkSeriesFiltered,
        isMixedAuthors,
    } = useLibraryPanel(onPdfClick);

    return (
        <>
            <LibraryHeader
                currentPath={currentPath}
                currentSource={currentSource}
                isSelectionMode={isSelectionMode}
                selectedCount={selectedItems.size}
                sortOrder={sortOrder}
                searchText={searchText}
                authorFilter={authorFilter}
                allAuthors={allAuthors}
                groupMode={groupMode}
                breadcrumbs={breadcrumbs}
                showHidden={showHidden}
                onUpClick={onUpClick}
                onToggleSelectionMode={toggleSelectionMode}
                onBulkSetAuthor={() => dialogs.open('bulkAuthor')}
                onBulkSetSeries={() => dialogs.open('bulkSeries')}
                bulkSeriesDisabled={isMixedAuthors}
                onBulkSetGenre={() => dialogs.open('bulkGenre')}
                onBulkToggleHidden={bulkActions.handleBulkToggleHidden}
                onBulkDelete={bulkActions.handleBulkDelete}
                onRegenThumbnailBulk={bulkActions.handleRegenThumbnailBulk}
                onMergePdfs={() => dialogs.open('merge')}
                onSortChange={setSortOrder}
                onSearchChange={setSearchText}
                onAuthorFilterChange={setAuthorFilter}
                onGroupModeChange={handleGroupModeChange}
                onToggleShowHidden={toggleShowHidden}
                readStateFilter={readStateFilter}
                onReadStateFilterChange={setReadStateFilter}
                onMetaRefresh={refreshMeta}
            />

            <LibraryDialogs
                currentPath={currentPath}
                currentSource={currentSource}
                selectedItems={selectedItems}
                renameTarget={renameTarget}
                onCloseRename={closeRenameDialog}
                onRenameItem={handleRename}
                isBulkAuthorOpen={dialogs.isOpen('bulkAuthor')}
                bulkAuthorAllAuthors={allAuthors}
                onCloseBulkAuthor={dialogs.close}
                onBulkApplyAuthors={bulkActions.handleBulkApplyAuthors}
                isMergeDialogOpen={dialogs.isOpen('merge')}
                onCloseMergeDialog={dialogs.close}
                onMergePdfs={bulkActions.handleMergePdfs}
                isBulkSeriesOpen={dialogs.isOpen('bulkSeries')}
                bulkSeriesNames={bulkActions.bulkSeriesNames}
                bulkSeriesExisting={bulkSeriesFiltered}
                onCloseBulkSeries={dialogs.close}
                onBulkAssignSeries={bulkActions.handleBulkAssignSeries}
                isBulkGenreOpen={dialogs.isOpen('bulkGenre')}
                allGenres={genres}
                onCloseBulkGenre={dialogs.close}
                onBulkApplyGenre={bulkActions.handleBulkApplyGenre}
            />

            <GenreFilterBar
                genres={genres}
                genreFilter={genreFilter}
                onGenreFilterChange={setGenreFilter}
                onReorder={reorderGenres}
                onAdd={addGenre}
                onRemove={removeGenre}
            />

            <div className="flex-1 bg-gray-100 dark:bg-gray-950 overflow-auto">
                <div className="w-full h-full p-6 overflow-y-auto">
                    <PdfGrid
                        pdfs={displayPdfs}
                        onPdfClick={handlePdfClick}
                        isSelectionMode={isSelectionMode}
                        selectedItems={selectedItems}
                        onToggleSelect={handleToggleSelect}
                        favorites={contextualFavorites}
                        onToggleFavorite={
                            authorFilter || seriesFilter ? handleTogglePin : undefined
                        }
                        onRename={openRenameDialog}
                        onRegenThumb={handleRegenThumb}
                        getAuthors={(name) => getAuthors(currentPath, name)}
                        onAuthorClick={setAuthorFilter}
                        getBadge={(name) => grouped.badgeByRepresentativeName.get(name) ?? null}
                        onGroupClick={(name) => {
                            const badge = grouped.badgeByRepresentativeName.get(name);
                            if (!badge) return;
                            if (badge.kind === 'series') {
                                setSeriesFilter(badge.groupId);
                            } else {
                                // 作者集合キーの最初の作者で絞り込む（複数作者は最初を採用）
                                const firstAuthor = badge.groupId.split('\n')[0];
                                setAuthorFilter(firstAuthor);
                            }
                        }}
                        onToggleHidden={bulkActions.handleToggleHiddenOne}
                        showHidden={showHidden}
                        getReadState={(name) => getReadState(currentPath, name)}
                        onEditSeries={seriesEdit.open}
                        dndEnabled={!!seriesFilter}
                        onReorder={bulkActions.handleSeriesReorder}
                    />
                </div>
            </div>

            <SeriesEditDialog
                open={seriesEdit.target !== null}
                targetName={seriesEdit.target ?? ''}
                current={seriesEdit.target ? getSeries(currentPath, seriesEdit.target) : null}
                allSeries={seriesEditFilteredSeries}
                onClose={seriesEdit.close}
                onAssign={seriesEdit.assign}
                onUnassign={seriesEdit.unassign}
            />

            <ToastContainer toasts={toasts} onDismiss={dismissToast} />
        </>
    );
}
