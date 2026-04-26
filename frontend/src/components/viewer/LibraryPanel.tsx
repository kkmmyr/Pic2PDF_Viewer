import { useState, useCallback, useEffect } from 'react';
import type { SortOrder, RegenerateThumbnailBulkResponse, MergePdfsResponse } from '../../types';
import { LibraryHeader, FolderGrid, PdfGrid, ToastContainer } from '../reader';
import { LibraryDialogs } from './LibraryDialogs';
import { useFavorites, useSortedPdfs, useBookMeta, useAutoFillAuthors, useLibraryFilter, useToast } from '../../hooks';
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

    const [isBulkAuthorOpen, setIsBulkAuthorOpen] = useState(false);
    const [isMergeDialogOpen, setIsMergeDialogOpen] = useState(false);

    // パスまたはソース変更時に検索テキスト・フィルターをリセット
    useEffect(() => {
        setSearchText('');
        setAuthorFilter('');
    }, [currentPath, currentSource]);

    const handleSortChange = useCallback((order: SortOrder) => {
        setSortOrder(order);
        setStorageJson(SORT_STORAGE_KEY, order);
    }, []);

    const { favorites, toggle: toggleFavorite } = useFavorites(currentSource);
    const sortedPdfs = useSortedPdfs(pdfs, sortOrder, favorites);

    const { getAuthors, updateAuthors, allAuthors, refreshMeta } = useBookMeta(currentSource);
    const { jobStatus: autoFillStatus, startAutoFill } = useAutoFillAuthors(currentSource, refreshMeta);
    const [autoFillMode, setAutoFillMode] = useState<'missing_only' | 'unknown_only' | 'overwrite_all'>('unknown_only');
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
        currentPath,
        getAuthors,
    });

    const handleBulkApplyAuthors = useCallback(async (authors: string[]) => {
        await updateAuthors(currentPath, Array.from(selectedItems), authors);
    }, [selectedItems, currentPath, updateAuthors]);

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
                allAuthors={allAuthors}
                onUpClick={onUpClick}
                onSourceChange={onSourceChange}
                onToggleSelectionMode={onToggleSelectionMode}
                onCreateFolder={onOpenCreateFolder}
                onMoveSelected={onMoveSelected}
                onBulkSetAuthor={() => setIsBulkAuthorOpen(true)}
                onRegenThumbnailBulk={handleRegenThumbnailBulk}
                onMergePdfs={() => setIsMergeDialogOpen(true)}
                onSortChange={handleSortChange}
                onSearchChange={setSearchText}
                onAuthorFilterChange={setAuthorFilter}
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
                isMergeDialogOpen={isMergeDialogOpen}
                onCloseMergeDialog={() => setIsMergeDialogOpen(false)}
                onMergePdfs={handleMergePdfs}
            />

            {/* サークル名自動登録バー */}
            <div className="px-4 py-2 bg-gray-50 dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800 flex items-center gap-3 min-h-[40px]">
                {autoFillStatus.status !== 'running' && (
                    <>
                        <button
                            onClick={async () => {
                                try {
                                    await startAutoFill(autoFillMode);
                                } catch (e: unknown) {
                                    showToast(
                                        e instanceof Error ? e.message : '自動登録の開始に失敗しました。Ollama と SearXNG が起動しているか確認してください。',
                                        'error'
                                    );
                                }
                            }}
                            className="text-xs px-3 py-1 rounded bg-indigo-600 hover:bg-indigo-700 text-white transition-colors shrink-0"
                        >
                            サークル名自動登録
                        </button>
                        <div className="flex items-center gap-3">
                            {(
                                [
                                    { value: 'missing_only', label: '未登録のみ' },
                                    { value: 'unknown_only', label: '作者不明のみ' },
                                    { value: 'overwrite_all', label: '全件上書き' },
                                ] as const
                            ).map(({ value, label }) => (
                                <label key={value} className="flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400 cursor-pointer select-none">
                                    <input
                                        type="radio"
                                        name="autoFillMode"
                                        value={value}
                                        checked={autoFillMode === value}
                                        onChange={() => setAutoFillMode(value)}
                                        className="accent-indigo-600"
                                    />
                                    {label}
                                </label>
                            ))}
                        </div>
                    </>
                )}
                {autoFillStatus.status === 'running' && (
                    <div className="flex-1 flex items-center gap-3">
                        <div className="flex-1">
                            <div className="text-xs text-gray-500 dark:text-gray-400 mb-1 truncate">
                                {autoFillStatus.done} / {autoFillStatus.total} 件 — {autoFillStatus.current}
                            </div>
                            <div className="h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                                <div
                                    className="h-full bg-indigo-500 rounded-full transition-all duration-500"
                                    style={{ width: autoFillStatus.total > 0 ? `${(autoFillStatus.done / autoFillStatus.total) * 100}%` : '0%' }}
                                />
                            </div>
                        </div>
                        <span className="text-xs text-gray-400 dark:text-gray-500 shrink-0">処理中…</span>
                    </div>
                )}
                {autoFillStatus.status === 'done' && (
                    <span className="text-xs text-green-600 dark:text-green-400 ml-2">
                        完了 — {autoFillStatus.done} 件登録、{autoFillStatus.skipped} 件スキップ
                    </span>
                )}
                {autoFillStatus.status === 'error' && (
                    <span className="text-xs text-red-500 dark:text-red-400 truncate ml-2">
                        エラー: {autoFillStatus.error}
                    </span>
                )}
            </div>

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
                        onPdfClick={onPdfClick}
                        isSelectionMode={isSelectionMode}
                        selectedItems={selectedItems}
                        onToggleSelect={onToggleSelect}
                        favorites={favorites}
                        onToggleFavorite={toggleFavorite}
                        onRename={onOpenRename}
                        onRegenThumb={handleRegenThumb}
                        getAuthors={(name) => getAuthors(currentPath, name)}
                        onAuthorClick={setAuthorFilter}
                    />
                </div>
            </div>
            <ToastContainer toasts={toasts} onDismiss={dismissToast} />
        </>
    );
}
