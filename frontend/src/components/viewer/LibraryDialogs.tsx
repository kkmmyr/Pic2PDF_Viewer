import type { LibrarySource, ExistingSeriesOption } from '../../types';
import { RenameDialog, BulkAuthorDialog, MergeDialog } from './';
import { BulkTagDialog } from './BulkTagDialog';
import { BulkSeriesAssignDialog } from './BulkSeriesAssignDialog';
import { BulkGenreDialog } from './BulkGenreDialog';

interface LibraryDialogsProps {
    currentPath: string;
    currentSource: LibrarySource;
    selectedItems: Set<string>;
    // Rename
    renameTarget: { name: string; isFolder: boolean } | null;
    onCloseRename: () => void;
    onRenameItem: (newName: string) => Promise<void>;
    // BulkAuthor
    isBulkAuthorOpen: boolean;
    bulkAuthorAllAuthors: string[];
    onCloseBulkAuthor: () => void;
    onBulkApplyAuthors: (authors: string[]) => Promise<void>;
    // BulkTag
    isBulkTagOpen: boolean;
    bulkTagInitial: string[];
    onCloseBulkTag: () => void;
    onBulkApplyTags: (tags: string[]) => Promise<void>;
    // Merge
    isMergeDialogOpen: boolean;
    onCloseMergeDialog: () => void;
    onMergePdfs: (outputName: string) => Promise<void>;
    // BulkSeriesAssign
    isBulkSeriesOpen: boolean;
    bulkSeriesNames: string[];
    bulkSeriesExisting: ExistingSeriesOption[];
    onCloseBulkSeries: () => void;
    onBulkAssignSeries: (params: {
        title: string;
        indexes: number[];
        id?: string;
    }) => Promise<void>;
    // BulkGenre
    isBulkGenreOpen: boolean;
    allGenres: string[];
    onCloseBulkGenre: () => void;
    onBulkApplyGenre: (genre: string) => Promise<void>;
}

export function LibraryDialogs({
    selectedItems,
    renameTarget,
    onCloseRename,
    onRenameItem,
    isBulkAuthorOpen,
    bulkAuthorAllAuthors,
    onCloseBulkAuthor,
    onBulkApplyAuthors,
    isBulkTagOpen,
    bulkTagInitial,
    onCloseBulkTag,
    onBulkApplyTags,
    isMergeDialogOpen,
    onCloseMergeDialog,
    onMergePdfs,
    isBulkSeriesOpen,
    bulkSeriesNames,
    bulkSeriesExisting,
    onCloseBulkSeries,
    onBulkAssignSeries,
    isBulkGenreOpen,
    allGenres,
    onCloseBulkGenre,
    onBulkApplyGenre,
}: LibraryDialogsProps) {
    const pdfItems = Array.from(selectedItems).filter((item) =>
        item.toLowerCase().endsWith('.pdf'),
    );

    return (
        <>
            <RenameDialog
                open={renameTarget !== null}
                currentName={renameTarget?.name ?? ''}
                isFolder={renameTarget?.isFolder ?? false}
                onClose={onCloseRename}
                onRename={onRenameItem}
            />

            <BulkAuthorDialog
                open={isBulkAuthorOpen}
                targetCount={selectedItems.size}
                allAuthors={bulkAuthorAllAuthors}
                onClose={onCloseBulkAuthor}
                onApply={onBulkApplyAuthors}
            />

            <BulkTagDialog
                open={isBulkTagOpen}
                targetCount={selectedItems.size}
                initialTags={bulkTagInitial}
                onClose={onCloseBulkTag}
                onApply={onBulkApplyTags}
            />

            <MergeDialog
                open={isMergeDialogOpen}
                selectedItems={pdfItems}
                onClose={onCloseMergeDialog}
                onMerge={onMergePdfs}
            />

            <BulkSeriesAssignDialog
                open={isBulkSeriesOpen}
                selectedNames={bulkSeriesNames}
                existingSeries={bulkSeriesExisting}
                onClose={onCloseBulkSeries}
                onAssign={onBulkAssignSeries}
            />

            <BulkGenreDialog
                open={isBulkGenreOpen}
                targetCount={selectedItems.size}
                allGenres={allGenres}
                onClose={onCloseBulkGenre}
                onApply={onBulkApplyGenre}
            />
        </>
    );
}
