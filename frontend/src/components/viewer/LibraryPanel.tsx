import { useState, useCallback, useEffect, useMemo } from 'react';
import { LibraryHeader, FolderGrid, PdfGrid, ToastContainer, GenreFilterBar } from '../reader';
import { LibraryDialogs } from './LibraryDialogs';
import { SeriesEditDialog } from './SeriesEditDialog';
import {
    useLibraryPins, useSortedPdfs, useBookMeta, useLibraryFilter, useToast,
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
        onBulkSelect,
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
        showUnreadOnly, toggleShowUnreadOnly,
        genreFilter, setGenreFilter,
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

    const { seriesPins, authorPins, toggleSeriesPin, toggleAuthorPin } = useLibraryPins(currentSource);
    const {
        meta, getAuthors, getTags, getSeries, getViewCount, getLastViewedAt, isHidden,
        recordView, updateAuthors, updateTags, setHidden,
        assignSeries, unassignSeries, reorderSeries,
        allAuthors, allTags, allGenres, allSeries, allSeriesWithStats, refreshMeta,
    } = useBookMeta(currentSource);
    const { toasts, showToast, dismissToast } = useToast();

    // ピン済み書籍の Set（favorites_first ソート用。シリーズ・作者ピン両方を含む）
    const pinnedBooks = useMemo(() => {
        const set = new Set<string>();
        for (const [key, entry] of Object.entries(meta)) {
            const isDirectChild = currentPath
                ? key.startsWith(currentPath + '/') && !key.slice(currentPath.length + 1).includes('/')
                : !key.includes('/');
            if (!isDirectChild) continue;
            const name = currentPath ? key.slice(currentPath.length + 1) : key;
            if (entry.series_id && seriesPins[entry.series_id] === name) { set.add(name); continue; }
            if (entry.authors?.length) {
                const ak = [...entry.authors].sort().join('\n');
                if (authorPins[ak] === name) set.add(name);
            }
        }
        return set;
    }, [meta, currentPath, seriesPins, authorPins]);

    // 文脈別お気に入りSet（PdfGrid の isFav 表示用）
    // seriesFilter 中はシリーズピンのみ、authorFilter 中は作者ピンのみ表示して混在を防ぐ
    const contextualFavorites = useMemo(() => {
        if (!seriesFilter && !authorFilter) return new Set<string>();
        const set = new Set<string>();
        for (const [key, entry] of Object.entries(meta)) {
            const isDirectChild = currentPath
                ? key.startsWith(currentPath + '/') && !key.slice(currentPath.length + 1).includes('/')
                : !key.includes('/');
            if (!isDirectChild) continue;
            const name = currentPath ? key.slice(currentPath.length + 1) : key;
            if (seriesFilter) {
                if (entry.series_id && seriesPins[entry.series_id] === name) set.add(name);
            } else {
                if (entry.authors?.length) {
                    const ak = [...entry.authors].sort().join('\n');
                    if (authorPins[ak] === name) set.add(name);
                }
            }
        }
        return set;
    }, [seriesFilter, authorFilter, meta, currentPath, seriesPins, authorPins]);

    const sortedPdfs = useSortedPdfs(
        pdfs,
        sortOrder,
        pinnedBooks,
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
        showUnreadOnly,
        genreFilter,
        currentPath,
        meta,
    });

    const { effectiveGroupMode, grouped, displayPdfs, breadcrumbs } = useLibraryDisplay({
        filteredPdfs,
        meta,
        currentPath,
        // 検索中は集約を解除して個別書籍を直接表示する
        groupMode: searchText.trim() ? 'none' : groupMode,
        authorFilter,
        seriesFilter,
        getSeries,
        clearAllDrilldown,
        setSeriesFilter,
        seriesPins,
        authorPins,
    });

    const bulkActions = useLibraryBulkActions({
        currentPath, currentSource, selectedItems, showHidden, seriesFilter,
        onClearSelection, onRefresh, showToast,
        bookMeta: { updateAuthors, updateTags, setHidden, assignSeries, reorderSeries },
    });

    void isHidden; // 将来 PdfGrid 内で個別判定する用に export 済（現状は filter 段階で除外）

    // seriesFilter 中 → シリーズ代表巻ピン、authorFilter 中 → 作者代表カードピン
    const handleTogglePin = useCallback((name: string) => {
        const key = currentPath ? `${currentPath}/${name}` : name;
        const entry = meta[key];
        if (!entry) return;
        if (seriesFilter) {
            if (entry.series_id) toggleSeriesPin(entry.series_id, name);
        } else if (authorFilter) {
            if (entry.authors?.length) toggleAuthorPin([...entry.authors].sort().join('\n'), name);
        }
    }, [currentPath, meta, seriesFilter, authorFilter, toggleSeriesPin, toggleAuthorPin]);

    // 集約カードをチェックしたときは全メンバーを一括選択/解除する
    const handleToggleSelect = useCallback((name: string) => {
        const members = grouped.membersByRepresentativeName.get(name);
        if (members && members.length > 0) {
            const allSelected = members.every(m => selectedItems.has(m.name));
            onBulkSelect(members.map(m => m.name), !allSelected);
        } else {
            onToggleSelect(name);
        }
    }, [grouped.membersByRepresentativeName, selectedItems, onBulkSelect, onToggleSelect]);

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
                onBulkDelete={bulkActions.handleBulkDelete}
                onRegenThumbnailBulk={bulkActions.handleRegenThumbnailBulk}
                onMergePdfs={() => setIsMergeDialogOpen(true)}
                onSortChange={setSortOrder}
                onSearchChange={setSearchText}
                onAuthorFilterChange={setAuthorFilter}
                onTagFilterChange={setTagFilter}
                onGroupModeChange={handleGroupModeChange}
                onToggleShowHidden={toggleShowHidden}
                showUnreadOnly={showUnreadOnly}
                onToggleUnreadOnly={toggleShowUnreadOnly}
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

            <GenreFilterBar
                allGenres={allGenres}
                genreFilter={genreFilter}
                onGenreFilterChange={setGenreFilter}
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
                        getUnreadCount={(dir) => {
                            const prefix = currentPath ? `${currentPath}/${dir}/` : `${dir}/`;
                            return Object.entries(meta).reduce((count, [key, entry]) => {
                                if (!key.startsWith(prefix)) return count;
                                if (key.slice(prefix.length).includes('/')) return count;
                                return (entry.view_count ?? 0) === 0 ? count + 1 : count;
                            }, 0);
                        }}
                    />
                    <PdfGrid
                        pdfs={displayPdfs}
                        onPdfClick={handlePdfClick}
                        isSelectionMode={isSelectionMode}
                        selectedItems={selectedItems}
                        onToggleSelect={handleToggleSelect}
                        favorites={contextualFavorites}
                        onToggleFavorite={(authorFilter || seriesFilter) ? handleTogglePin : undefined}
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
