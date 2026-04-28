import { useState, useCallback, useEffect } from 'react';
import type { SortOrder, RegenerateThumbnailBulkResponse, MergePdfsResponse } from '../../types';
import { LibraryHeader, FolderGrid, PdfGrid, ToastContainer } from '../reader';
import { LibraryDialogs } from './LibraryDialogs';
import { AutoFillAuthorsBar } from './AutoFillAuthorsBar';
import { useFavorites, useSortedPdfs, useBookMeta, useLibraryFilter, useToast } from '../../hooks';
import { useLibraryContext } from '../../contexts/LibraryContext';
import { API_ENDPOINTS } from '../../config/api';
import apiClient from '../../config/api_client';
import { STORAGE_KEYS } from '../../constants';
import { getStorageJson, setStorageJson } from '../../utils/storage';

const SORT_STORAGE_KEY = STORAGE_KEYS.LIBRARY_SORT;

function readStoredSort(): SortOrder {
    return getStorageJson<SortOrder>(SORT_STORAGE_KEY, 'name_asc');
}

/**
 * ライブラリ一覧ビュー。
 * フォルダ/PDF グリッド・ヘッダー・各ダイアログを管理する。
 * お気に入り・並び替え・タイトル検索・作者フィルター・メタデータ管理もこのコンポーネントで完結させる。
 */
export function LibraryPanel() {
    const {
        pdfs, directories, currentPath, currentSource,
        isSelectionMode, selectedItems,
        isMoveDialogOpen, isCreateFolderOpen, renameTarget,
        onPdfClick, onFolderClick, onUpClick, onSourceChange,
        onToggleSelectionMode, onToggleSelect,
        onOpenCreateFolder, onCloseCreateFolder, onCreateFolder,
        onMoveSelected, onCloseMoveDialog, onMoveItems,
        onOpenRename, onCloseRename, onRenameItem, onRefresh,
    } = useLibraryContext();

    const [sortOrder, setSortOrder] = useState<SortOrder>(readStoredSort);
    const [searchText, setSearchText] = useState('');
    const [authorFilter, setAuthorFilter] = useState('');
    const [tagFilter, setTagFilter] = useState('');

    const [isBulkAuthorOpen, setIsBulkAuthorOpen] = useState(false);
    const [isBulkTagOpen, setIsBulkTagOpen] = useState(false);
    const [isMergeDialogOpen, setIsMergeDialogOpen] = useState(false);

    // パスまたはソース変更時に検索テキスト・フィルターをリセット
    useEffect(() => {
        setSearchText('');
        setAuthorFilter('');
        setTagFilter('');
    }, [currentPath, currentSource]);

    const handleSortChange = useCallback((order: SortOrder) => {
        setSortOrder(order);
        setStorageJson(SORT_STORAGE_KEY, order);
    }, []);

    const { favorites, toggle: toggleFavorite } = useFavorites(currentSource);
    const {
        meta, getAuthors, getTags, getViewCount, getLastViewedAt,
        recordView, updateAuthors, updateTags, allAuthors, allTags, refreshMeta,
    } = useBookMeta(currentSource);
    const sortedPdfs = useSortedPdfs(
        pdfs,
        sortOrder,
        favorites,
        (name) => getViewCount(currentPath, name),
        (name) => getLastViewedAt(currentPath, name),
    );

    const handlePdfClick = useCallback((name: string) => {
        recordView(currentPath, name);
        onPdfClick(name);
    }, [recordView, currentPath, onPdfClick]);
    const { toasts, showToast, dismissToast } = useToast();

    const handleRegenThumb = useCallback(async (name: string) => {
        await apiClient.post(API_ENDPOINTS.REGENERATE_THUMBNAIL, {
            path: currentPath,
            name,
            source: currentSource,
        });
        onRefresh();
    }, [currentPath, currentSource, onRefresh]);

    const { filteredPdfs, filteredDirs } = useLibraryFilter({
        pdfs: sortedPdfs,
        directories,
        searchText,
        authorFilter,
        tagFilter,
        currentPath,
        meta,
    });

    const handleBulkApplyAuthors = useCallback(async (authors: string[]) => {
        await updateAuthors(currentPath, Array.from(selectedItems), authors);
    }, [selectedItems, currentPath, updateAuthors]);

    const handleBulkApplyTags = useCallback(async (tags: string[]) => {
        const pdfNames = Array.from(selectedItems).filter(item => item.toLowerCase().endsWith('.pdf'));
        await updateTags(currentPath, pdfNames, tags);
    }, [selectedItems, currentPath, updateTags]);

    // 1冊だけ選択中ならその書籍の現在タグを初期表示する
    const bulkTagInitial = (() => {
        const pdfNames = Array.from(selectedItems).filter(item => item.toLowerCase().endsWith('.pdf'));
        if (pdfNames.length !== 1) return [];
        return getTags(currentPath, pdfNames[0]);
    })();

    const handleRegenThumbnailBulk = useCallback(async () => {
        const names = Array.from(selectedItems).filter(item => item.toLowerCase().endsWith('.pdf'));
        if (names.length === 0) return;
        try {
            const data = await apiClient.post<unknown, RegenerateThumbnailBulkResponse>(
                API_ENDPOINTS.REGENERATE_THUMBNAIL_BULK,
                { names, path: currentPath, source: currentSource }
            );
            onRefresh();
            if (data.failed.length > 0) {
                showToast(`${data.succeeded.length} 件再生成完了。失敗: ${data.failed.join(', ')}`, 'error');
            }
        } catch (e: unknown) {
            showToast(e instanceof Error ? e.message : 'サムネイル再生成に失敗しました。', 'error');
        }
    }, [selectedItems, currentPath, currentSource, onRefresh]);

    const handleMergePdfs = useCallback(async (outputName: string) => {
        const names = Array.from(selectedItems).filter(item => item.toLowerCase().endsWith('.pdf'));
        await apiClient.post<unknown, MergePdfsResponse>(
            API_ENDPOINTS.MERGE_PDFS,
            { names, output_name: outputName, path: currentPath, source: currentSource }
        );
        onRefresh();
    }, [selectedItems, currentPath, currentSource, onRefresh]);

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
                tagFilter={tagFilter}
                allAuthors={allAuthors}
                allTags={allTags}
                onUpClick={onUpClick}
                onSourceChange={onSourceChange}
                onToggleSelectionMode={onToggleSelectionMode}
                onCreateFolder={onOpenCreateFolder}
                onMoveSelected={onMoveSelected}
                onBulkSetAuthor={() => setIsBulkAuthorOpen(true)}
                onBulkSetTag={() => setIsBulkTagOpen(true)}
                onRegenThumbnailBulk={handleRegenThumbnailBulk}
                onMergePdfs={() => setIsMergeDialogOpen(true)}
                onSortChange={handleSortChange}
                onSearchChange={setSearchText}
                onAuthorFilterChange={setAuthorFilter}
                onTagFilterChange={setTagFilter}
            />

            <LibraryDialogs
                currentPath={currentPath}
                currentSource={currentSource}
                selectedItems={selectedItems}
                isCreateFolderOpen={isCreateFolderOpen}
                onCloseCreateFolder={onCloseCreateFolder}
                onCreateFolder={onCreateFolder}
                renameTarget={renameTarget}
                onCloseRename={onCloseRename}
                onRenameItem={onRenameItem}
                isMoveDialogOpen={isMoveDialogOpen}
                onCloseMoveDialog={onCloseMoveDialog}
                onMoveItems={onMoveItems}
                isBulkAuthorOpen={isBulkAuthorOpen}
                onCloseBulkAuthor={() => setIsBulkAuthorOpen(false)}
                onBulkApplyAuthors={handleBulkApplyAuthors}
                isBulkTagOpen={isBulkTagOpen}
                bulkTagInitial={bulkTagInitial}
                onCloseBulkTag={() => setIsBulkTagOpen(false)}
                onBulkApplyTags={handleBulkApplyTags}
                isMergeDialogOpen={isMergeDialogOpen}
                onCloseMergeDialog={() => setIsMergeDialogOpen(false)}
                onMergePdfs={handleMergePdfs}
            />

            <AutoFillAuthorsBar source={currentSource} onComplete={refreshMeta} />

            <div className="flex-1 bg-gray-100 dark:bg-gray-950 overflow-auto">
                <div className="w-full h-full p-6 overflow-y-auto">
                    <FolderGrid
                        directories={filteredDirs}
                        onFolderClick={onFolderClick}
                        isSelectionMode={isSelectionMode}
                        selectedItems={selectedItems}
                        onToggleSelect={onToggleSelect}
                        onRename={(name) => onOpenRename(name, true)}
                    />
                    <PdfGrid
                        pdfs={filteredPdfs}
                        onPdfClick={handlePdfClick}
                        isSelectionMode={isSelectionMode}
                        selectedItems={selectedItems}
                        onToggleSelect={onToggleSelect}
                        favorites={favorites}
                        onToggleFavorite={toggleFavorite}
                        onRename={onOpenRename}
                        onRegenThumb={handleRegenThumb}
                        getAuthors={(name) => getAuthors(currentPath, name)}
                        onAuthorClick={setAuthorFilter}
                        getTags={(name) => getTags(currentPath, name)}
                        onTagClick={setTagFilter}
                    />
                </div>
            </div>
            <ToastContainer toasts={toasts} onDismiss={dismissToast} />
        </>
    );
}
