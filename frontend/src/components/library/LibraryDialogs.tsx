import { useLibraryPanelContext } from '../../contexts/LibraryPanelContext';
import { RenameDialog, BulkAuthorDialog, MergeDialog } from './';
import { BulkSeriesAssignDialog } from './BulkSeriesAssignDialog';
import { BulkGenreDialog } from './BulkGenreDialog';

export function LibraryDialogs() {
    const {
        currentPath,
        currentSource,
        selectedItems,
        renameTarget,
        closeRenameDialog,
        handleRename,
        dialogs,
        allAuthors,
        bulkActions,
        bulkSeriesFiltered,
        genres,
    } = useLibraryPanelContext();

    const pdfItems = Array.from(selectedItems).filter((item) =>
        item.toLowerCase().endsWith('.pdf'),
    );

    return (
        <>
            <RenameDialog
                open={renameTarget !== null}
                currentName={renameTarget?.name ?? ''}
                isFolder={renameTarget?.isFolder ?? false}
                onClose={closeRenameDialog}
                onRename={handleRename}
            />

            <BulkAuthorDialog
                open={dialogs.isOpen('bulkAuthor')}
                targetCount={selectedItems.size}
                allAuthors={allAuthors}
                onClose={dialogs.close}
                onApply={bulkActions.handleBulkApplyAuthors}
            />

            <MergeDialog
                open={dialogs.isOpen('merge')}
                selectedItems={pdfItems}
                onClose={dialogs.close}
                onMerge={bulkActions.handleMergePdfs}
            />

            <BulkSeriesAssignDialog
                open={dialogs.isOpen('bulkSeries')}
                selectedNames={bulkActions.bulkSeriesNames}
                existingSeries={bulkSeriesFiltered}
                source={currentSource}
                path={currentPath}
                onClose={dialogs.close}
                onAssign={bulkActions.handleBulkAssignSeries}
            />

            <BulkGenreDialog
                open={dialogs.isOpen('bulkGenre')}
                targetCount={selectedItems.size}
                allGenres={genres}
                onClose={dialogs.close}
                onApply={bulkActions.handleBulkApplyGenre}
            />
        </>
    );
}
