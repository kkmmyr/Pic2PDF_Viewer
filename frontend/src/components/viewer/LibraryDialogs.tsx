import type { LibrarySource, ExistingSeriesOption } from '../../types';
import { MoveDialog } from '../reader';
import { CreateFolderDialog, RenameDialog, BulkAuthorDialog, MergeDialog } from './';
import { BulkTagDialog } from './BulkTagDialog';
import { BulkSeriesAssignDialog } from './BulkSeriesAssignDialog';

export interface LibraryDialogsProps {
    currentPath: string;
    currentSource: LibrarySource;
    selectedItems: Set<string>;
    // CreateFolder
    isCreateFolderOpen: boolean;
    onCloseCreateFolder: () => void;
    onCreateFolder: (name: string) => Promise<void>;
    // Rename
    renameTarget: { name: string; isFolder: boolean } | null;
    onCloseRename: () => void;
    onRenameItem: (newName: string) => Promise<void>;
    // Move
    isMoveDialogOpen: boolean;
    onCloseMoveDialog: () => void;
    onMoveItems: (destination: string) => Promise<void>;
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
    onBulkAssignSeries: (params: { title: string; indexes: number[]; id?: string }) => Promise<void>;
}

export function LibraryDialogs({
    currentPath, currentSource, selectedItems,
    isCreateFolderOpen, onCloseCreateFolder, onCreateFolder,
    renameTarget, onCloseRename, onRenameItem,
    isMoveDialogOpen, onCloseMoveDialog, onMoveItems,
    isBulkAuthorOpen, bulkAuthorAllAuthors, onCloseBulkAuthor, onBulkApplyAuthors,
    isBulkTagOpen, bulkTagInitial, onCloseBulkTag, onBulkApplyTags,
    isMergeDialogOpen, onCloseMergeDialog, onMergePdfs,
    isBulkSeriesOpen, bulkSeriesNames, bulkSeriesExisting, onCloseBulkSeries, onBulkAssignSeries,
}: LibraryDialogsProps) {
    const pdfItems = Array.from(selectedItems).filter(item => item.toLowerCase().endsWith('.pdf'));

    return (
        <>
            <CreateFolderDialog
                open={isCreateFolderOpen}
                onClose={onCloseCreateFolder}
                onCreate={onCreateFolder}
            />

            <RenameDialog
                open={renameTarget !== null}
                currentName={renameTarget?.name ?? ''}
                isFolder={renameTarget?.isFolder ?? false}
                onClose={onCloseRename}
                onRename={onRenameItem}
            />

            <MoveDialog
                open={isMoveDialogOpen}
                onClose={onCloseMoveDialog}
                onMove={onMoveItems}
                currentSource={currentSource}
                sourcePath={currentPath}
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
        </>
    );
}
