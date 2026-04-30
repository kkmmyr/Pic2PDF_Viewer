import { useState, useCallback, useEffect } from 'react';
import { LibraryHeader, FolderGrid, PdfGrid, ToastContainer } from '../reader';
import { LibraryDialogs } from './LibraryDialogs';
import { SeriesEditDialog } from './SeriesEditDialog';
import {
    useFavorites, useSortedPdfs, useBookMeta, useLibraryFilter, useToast,
    useUrlFilters, useLibrarySettings, useLibraryBulkActions, useLibraryDisplay,
} from '../../hooks';
import { useLibraryContext } from '../../contexts/LibraryContext';
import { API_ENDPOINTS } from '../../config/api';
import apiClient from '../../config/api_client';

/**
 * ライブラリ一覧ビュー。
 * フォルダ/PDF グリッド・ヘッダー・各ダイアログを管理する。
 *
 * 大半のロジックは責務別カスタムフックに委譲し、本体は合成 + JSX に集中する:
 * - `useUrlFilters`: author/tag/series の URL クエリ同期
 * - `useLibrarySettings`: sort/groupMode/showHidden の localStorage 永続化
 * - `useLibraryBulkActions`: 一括操作 7 種（authors/tags/hidden/thumbnail/merge/series）
 * - `useLibraryDisplay`: effectiveGroupMode / displayPdfs / breadcrumbs の派生計算
 */
export function LibraryPanel() {
    const {
        pdfs, directories, selectedPdf, currentPath, currentSource,
        isSelectionMode, selectedItems,
        isMoveDialogOpen, isCreateFolderOpen, renameTarget,
        onPdfClick, onFolderClick, onUpClick, onSourceChange,
        onToggleSelectionMode, onClearSelection, onToggleSelect,
        onOpenCreateFolder, onCloseCreateFolder, onCreateFolder,
        onMoveSelected, onCloseMoveDialog, onMoveItems,
        onOpenRename, onCloseRename, onRenameItem, onRefresh,
    } = useLibraryContext();

    const [searchText, setSearchText] = useState('');
    const [seriesEditTarget, setSeriesEditTarget] = useState<string | null>(null);
    const [isBulkAuthorOpen, setIsBulkAuthorOpen] = useState(false);
    const [isBulkTagOpen, setIsBulkTagOpen] = useState(false);
    const [isMergeDialogOpen, setIsMergeDialogOpen] = useState(false);
    const [isBulkSeriesOpen, setIsBulkSeriesOpen] = useState(false);

    const {
        authorFilter, tagFilter, seriesFilter,
        setAuthorFilter, setTagFilter, setSeriesFilter,
        clearAllDrilldown,
    } = useUrlFilters();

    const {
        sortOrder, setSortOrder,
        groupMode, setGroupMode,
        showHidden, toggleShowHidden,
    } = useLibrarySettings();

    // パスまたはソース変更時に検索テキストをリセット。
    // author/tag/series は URL 同期されており、useUrlState の navigate
    // メソッドが setSearchParams({ path, source }) で全置換するため自動クリアされる。
    useEffect(() => {
        setSearchText('');
    }, [currentPath, currentSource]);

    // s キー: 選択モードをトグル（リーダーが開いている間・入力中・修飾キー付きは無効）
    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if (selectedPdf !== null) return;
            if (e.key !== 's') return;
            const target = e.target as HTMLElement;
            const tag = target.tagName;
            if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target.isContentEditable) return;
            if (e.ctrlKey || e.metaKey || e.altKey) return;
            e.preventDefault();
            onToggleSelectionMode();
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [selectedPdf, onToggleSelectionMode]);

    const handleGroupModeChange = useCallback((mode: typeof groupMode) => {
        setGroupMode(mode);
        // モード切替時にドリルダウン中のシリーズフィルターは解除（一覧の意味が変わるため）
        setSeriesFilter('');
    }, [setGroupMode, setSeriesFilter]);

    const { favorites, toggle: toggleFavorite } = useFavorites(currentSource);
    const {
        meta, getAuthors, getTags, getSeries, getViewCount, getLastViewedAt, isHidden,
        recordView, updateAuthors, updateTags, setHidden,
        assignSeries, unassignSeries, reorderSeries,
        allAuthors, allTags, allSeries, allSeriesWithStats, refreshMeta,
    } = useBookMeta(currentSource);
    const { toasts, showToast, dismissToast } = useToast();

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
        seriesFilter,
        showHidden,
        currentPath,
        meta,
    });

    const { effectiveGroupMode: _effectiveGroupMode, grouped, displayPdfs, breadcrumbs } = useLibraryDisplay({
        filteredPdfs,
        meta,
        currentPath,
        groupMode,
        authorFilter,
        seriesFilter,
        getSeries,
        clearAllDrilldown,
        setSeriesFilter,
    });
    void _effectiveGroupMode; // useLibraryDisplay 内で useLibraryGrouping に渡すための内部値（外には不要）

    const bulkActions = useLibraryBulkActions({
        currentPath, currentSource, selectedItems, showHidden, seriesFilter,
        onClearSelection, onRefresh, showToast,
        bookMeta: { updateAuthors, updateTags, setHidden, assignSeries, reorderSeries },
    });

    void isHidden; // 将来 PdfGrid 内で個別判定する用に export 済（現状は filter 段階で除外）

    // 1冊だけ選択中ならその書籍の現在タグを初期表示する
    const bulkTagInitial = (() => {
        if (bulkActions.bulkSeriesNames.length !== 1) return [];
        return getTags(currentPath, bulkActions.bulkSeriesNames[0]);
    })();

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
                groupMode={groupMode}
                breadcrumbs={breadcrumbs}
                showHidden={showHidden}
                onUpClick={onUpClick}
                onSourceChange={onSourceChange}
                onToggleSelectionMode={onToggleSelectionMode}
                onCreateFolder={onOpenCreateFolder}
                onMoveSelected={onMoveSelected}
                onBulkSetAuthor={() => setIsBulkAuthorOpen(true)}
                onBulkSetTag={() => setIsBulkTagOpen(true)}
                onBulkSetSeries={() => setIsBulkSeriesOpen(true)}
                onBulkToggleHidden={bulkActions.handleBulkToggleHidden}
                onRegenThumbnailBulk={bulkActions.handleRegenThumbnailBulk}
                onMergePdfs={() => setIsMergeDialogOpen(true)}
                onSortChange={setSortOrder}
                onSearchChange={setSearchText}
                onAuthorFilterChange={setAuthorFilter}
                onTagFilterChange={setTagFilter}
                onGroupModeChange={handleGroupModeChange}
                onToggleShowHidden={toggleShowHidden}
                onMetaRefresh={refreshMeta}
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
                bulkAuthorAllAuthors={allAuthors}
                onCloseBulkAuthor={() => setIsBulkAuthorOpen(false)}
                onBulkApplyAuthors={bulkActions.handleBulkApplyAuthors}
                isBulkTagOpen={isBulkTagOpen}
                bulkTagInitial={bulkTagInitial}
                onCloseBulkTag={() => setIsBulkTagOpen(false)}
                onBulkApplyTags={bulkActions.handleBulkApplyTags}
                isMergeDialogOpen={isMergeDialogOpen}
                onCloseMergeDialog={() => setIsMergeDialogOpen(false)}
                onMergePdfs={bulkActions.handleMergePdfs}
                isBulkSeriesOpen={isBulkSeriesOpen}
                bulkSeriesNames={bulkActions.bulkSeriesNames}
                bulkSeriesExisting={allSeriesWithStats}
                onCloseBulkSeries={() => setIsBulkSeriesOpen(false)}
                onBulkAssignSeries={bulkActions.handleBulkAssignSeries}
            />

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
                        pdfs={displayPdfs}
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
                        getIsUnread={(name) => getViewCount(currentPath, name) === 0}
                        onEditSeries={setSeriesEditTarget}
                        dndEnabled={!!seriesFilter}
                        onReorder={bulkActions.handleSeriesReorder}
                    />
                </div>
            </div>
            <SeriesEditDialog
                open={seriesEditTarget !== null}
                targetName={seriesEditTarget ?? ''}
                current={seriesEditTarget ? getSeries(currentPath, seriesEditTarget) : null}
                allSeries={allSeries}
                onClose={() => setSeriesEditTarget(null)}
                onAssign={async (params) => {
                    if (!seriesEditTarget) return;
                    try {
                        await assignSeries(currentPath, [seriesEditTarget], params);
                    } catch (e: unknown) {
                        showToast(e instanceof Error ? e.message : 'シリーズ割り当てに失敗しました。', 'error');
                        throw e;
                    }
                }}
                onUnassign={async () => {
                    if (!seriesEditTarget) return;
                    try {
                        await unassignSeries(currentPath, [seriesEditTarget]);
                    } catch (e: unknown) {
                        showToast(e instanceof Error ? e.message : 'シリーズ解除に失敗しました。', 'error');
                        throw e;
                    }
                }}
            />

            <ToastContainer toasts={toasts} onDismiss={dismissToast} />
        </>
    );
}
