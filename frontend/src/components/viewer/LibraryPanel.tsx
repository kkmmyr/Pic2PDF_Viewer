import { useState, useCallback, useMemo, useEffect } from 'react';
import type { PdfFile, LibrarySource, SortOrder, RegenerateThumbnailBulkResponse, MergePdfsResponse } from '../../types';
import { LibraryHeader, FolderGrid, PdfGrid } from '../reader';
import { LibraryDialogs } from './LibraryDialogs';
import { useFavorites, useSortedPdfs, useBookMeta, useAutoFillAuthors } from '../../hooks';
import { API_ENDPOINTS } from '../../config/api';
import apiClient from '../../config/api_client';
import { STORAGE_KEYS } from '../../constants';
import { getStorageJson, setStorageJson } from '../../utils/storage';

const SORT_STORAGE_KEY = STORAGE_KEYS.LIBRARY_SORT;

function readStoredSort(): SortOrder {
    return getStorageJson<SortOrder>(SORT_STORAGE_KEY, 'name_asc');
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
    renameTarget: { name: string; isFolder: boolean } | null;
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
    onOpenRename: (name: string, isFolder?: boolean) => void;
    onCloseRename: () => void;
    onRenameItem: (newName: string) => Promise<void>;
    onRefresh: () => void;
}

/**
 * ライブラリ一覧ビュー。
 * フォルダ/PDF グリッド・ヘッダー・各ダイアログを管理する。
 * お気に入り・並び替え・タイトル検索・作者フィルター・メタデータ管理もこのコンポーネントで完結させる。
 */
export function LibraryPanel({
    pdfs, directories, currentPath, currentSource,
    isSelectionMode, selectedItems,
    isMoveDialogOpen, isCreateFolderOpen, renameTarget,
    onPdfClick, onFolderClick, onUpClick, onSourceChange,
    onToggleSelectionMode, onToggleSelect,
    onOpenCreateFolder, onCloseCreateFolder, onCreateFolder,
    onMoveSelected, onCloseMoveDialog, onMoveItems,
    onOpenRename, onCloseRename, onRenameItem, onRefresh,
}: LibraryPanelProps) {
    const [sortOrder, setSortOrder] = useState<SortOrder>(readStoredSort);
    const [searchText, setSearchText] = useState('');
    const [authorFilter, setAuthorFilter] = useState('');

    // 一括作者設定ダイアログ
    const [isBulkAuthorOpen, setIsBulkAuthorOpen] = useState(false);

    // PDF結合ダイアログ
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

    // メタデータ（作者名）管理
    const { getAuthors, updateAuthors, allAuthors, refreshMeta } = useBookMeta(currentSource);

    // サークル名自動登録
    const { jobStatus: autoFillStatus, startAutoFill } = useAutoFillAuthors(currentSource, refreshMeta);
    const [autoFillOverwrite, setAutoFillOverwrite] = useState(false);

    const handleRegenThumb = useCallback(async (name: string) => {
        await apiClient.post(API_ENDPOINTS.REGENERATE_THUMBNAIL, {
            path: currentPath,
            name,
            source: currentSource,
        });
        onRefresh();
    }, [currentPath, currentSource, onRefresh]);

    // タイトル検索 + 作者フィルター
    const filteredPdfs = useMemo(() => {
        let result = sortedPdfs;

        if (searchText.trim()) {
            const lower = searchText.toLowerCase();
            result = result.filter(p =>
                p.name.toLowerCase().includes(lower) ||
                getAuthors(currentPath, p.name).some(a => a.toLowerCase().includes(lower))
            );
        }

        if (authorFilter) {
            result = result.filter(p => {
                const authors = getAuthors(currentPath, p.name);
                return authors.includes(authorFilter);
            });
        }

        return result;
    }, [sortedPdfs, searchText, authorFilter, getAuthors, currentPath]);

    const filteredDirs = useMemo(() => {
        if (!searchText.trim()) return directories;
        const lower = searchText.toLowerCase();
        return directories.filter(d => d.toLowerCase().includes(lower));
    }, [directories, searchText]);

    // 一括作者設定
    const handleBulkApplyAuthors = useCallback(async (authors: string[]) => {
        await updateAuthors(currentPath, Array.from(selectedItems), authors);
    }, [selectedItems, currentPath, updateAuthors]);

    // サムネイル一括再生成
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
                alert(`${data.succeeded.length} 件再生成完了。失敗: ${data.failed.join(', ')}`);
            }
        } catch (e: unknown) {
            alert(e instanceof Error ? e.message : 'サムネイル再生成に失敗しました。');
        }
    }, [selectedItems, currentPath, currentSource, onRefresh]);

    // PDF結合
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
                            onClick={() => startAutoFill(autoFillOverwrite)}
                            className="text-xs px-3 py-1 rounded bg-indigo-600 hover:bg-indigo-700 text-white transition-colors shrink-0"
                        >
                            サークル名自動登録
                        </button>
                        <label className="flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400 cursor-pointer select-none">
                            <input
                                type="checkbox"
                                checked={autoFillOverwrite}
                                onChange={e => setAutoFillOverwrite(e.target.checked)}
                                className="w-3 h-3 accent-indigo-600"
                            />
                            登録済みも上書き
                        </label>
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
                    />
                </div>
            </div>

        </>
    );
}
