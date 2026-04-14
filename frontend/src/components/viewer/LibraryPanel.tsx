import { useState, useCallback, useMemo } from 'react';
import type { PdfFile, LibrarySource, SortOrder } from '../../types';
import { LibraryHeader, FolderGrid, PdfGrid, MoveDialog } from '../reader';
import { CreateFolderDialog, RenameDialog } from './';
import { useFavorites, useSortedPdfs } from '../../hooks';

const SORT_STORAGE_KEY = 'librarySortOrder';

function readStoredSort(): SortOrder {
    try {
        const v = localStorage.getItem(SORT_STORAGE_KEY);
        if (v) return v as SortOrder;
    } catch { /* ignore */ }
    return 'name_asc';
}

interface LibraryPanelProps {
    pdfs: PdfFile[];
    directories: string[];
    currentPath: string;
    currentSource: LibrarySource;
    // 選択モード
    isSelectionMode: boolean;
    selectedItems: Set<string>;
    // 移動ダイアログ
    isMoveDialogOpen: boolean;
    // フォルダ作成ダイアログ
    isCreateFolderOpen: boolean;
    // リネームダイアログ
    renameTarget: string | null;
    // コールバック
    onPdfClick: (name: string) => void;
    onFolderClick: (name: string) => void;
    onUpClick: () => void;
    onSourceChange: (source: LibrarySource) => void;
    onToggleSelectionMode: () => void;
    onToggleSelect: (item: string) => void;
    onOpenCreateFolder: () => void;
    onCloseCreateFolder: () => void;
    onCreateFolder: (name: string) => Promise<void>;
    onMoveSelected: () => void;
    onCloseMoveDialog: () => void;
    onMoveItems: (destination: string) => Promise<void>;
    onOpenRename: (name: string) => void;
    onCloseRename: () => void;
    onRenameItem: (newName: string) => Promise<void>;
}

/**
 * ライブラリ一覧ビュー。
 * フォルダ/PDF グリッド・ヘッダー・移動ダイアログ・フォルダ作成ダイアログ・リネームダイアログを管理する。
 * お気に入り・並び替え・タイトル検索もこのコンポーネントで完結させる。
 */
export function LibraryPanel({
    pdfs, directories, currentPath, currentSource,
    isSelectionMode, selectedItems,
    isMoveDialogOpen, isCreateFolderOpen, renameTarget,
    onPdfClick, onFolderClick, onUpClick, onSourceChange,
    onToggleSelectionMode, onToggleSelect,
    onOpenCreateFolder, onCloseCreateFolder, onCreateFolder,
    onMoveSelected, onCloseMoveDialog, onMoveItems,
    onOpenRename, onCloseRename, onRenameItem,
}: LibraryPanelProps) {
    const [sortOrder, setSortOrder] = useState<SortOrder>(readStoredSort);
    const [searchText, setSearchText] = useState('');

    const handleSortChange = useCallback((order: SortOrder) => {
        setSortOrder(order);
        try { localStorage.setItem(SORT_STORAGE_KEY, order); } catch { /* ignore */ }
    }, []);

    const { favorites, toggle: toggleFavorite } = useFavorites(currentSource);
    const sortedPdfs = useSortedPdfs(pdfs, sortOrder, favorites);

    const filteredPdfs = useMemo(() => {
        if (!searchText.trim()) return sortedPdfs;
        const lower = searchText.toLowerCase();
        return sortedPdfs.filter(p => p.name.toLowerCase().includes(lower));
    }, [sortedPdfs, searchText]);

    const filteredDirs = useMemo(() => {
        if (!searchText.trim()) return directories;
        const lower = searchText.toLowerCase();
        return directories.filter(d => d.toLowerCase().includes(lower));
    }, [directories, searchText]);

    return (
        <>
            <LibraryHeader
                currentPath={currentPath}
                currentSource={currentSource}
                isSelectionMode={isSelectionMode}
                selectedCount={selectedItems.size}
                sortOrder={sortOrder}
                searchText={searchText}
                onUpClick={onUpClick}
                onSourceChange={onSourceChange}
                onToggleSelectionMode={onToggleSelectionMode}
                onCreateFolder={onOpenCreateFolder}
                onMoveSelected={onMoveSelected}
                onSortChange={handleSortChange}
                onSearchChange={setSearchText}
            />

            <CreateFolderDialog
                open={isCreateFolderOpen}
                onClose={onCloseCreateFolder}
                onCreate={onCreateFolder}
            />

            <RenameDialog
                open={renameTarget !== null}
                currentName={renameTarget ?? ''}
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

            <div className="flex-1 bg-gray-100 dark:bg-gray-950 overflow-auto">
                <div className="w-full h-full p-6 overflow-y-auto">
                    <FolderGrid
                        directories={filteredDirs}
                        onFolderClick={onFolderClick}
                        isSelectionMode={isSelectionMode}
                        selectedItems={selectedItems}
                        onToggleSelect={onToggleSelect}
                    />
                    <PdfGrid
                        pdfs={filteredPdfs}
                        onPdfClick={onPdfClick}
                        isSelectionMode={isSelectionMode}
                        selectedItems={selectedItems}
                        onToggleSelect={onToggleSelect}
                        favorites={favorites}
                        onToggleFavorite={toggleFavorite}
                        onRename={onOpenRename}
                    />
                </div>
            </div>
        </>
    );
}
