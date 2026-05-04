import { useState, useCallback, useEffect } from 'react';
import { LibraryHeader, PdfGrid, ToastContainer, GenreFilterBar } from '../reader';
import { LibraryDialogs } from './LibraryDialogs';
import { SeriesEditDialog } from './SeriesEditDialog';
import {
    useLibraryPins, useSortedPdfs, useBookMeta, useLibraryFilter, useToast,
    useUrlFilters, useLibrarySettings, useLibraryBulkActions, useLibraryDisplay, useGenres,
} from '../../hooks';
import { usePinnedBookSets } from '../../hooks/usePinnedBookSets';
import { useSeriesAuthorFilter } from '../../hooks/useSeriesAuthorFilter';
import { useDialogToggles } from '../../hooks/useDialogToggles';
import { useAsyncToast } from '../../hooks/useAsyncToast';
import { useLibraryContext } from '../../contexts/LibraryContext';
import { API_ENDPOINTS } from '../../config/api';
import apiClient from '../../config/api_client';

type BulkDialogKey = 'bulkAuthor' | 'bulkTag' | 'merge' | 'bulkSeries' | 'bulkGenre';

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
        pdfs, selectedPdf, currentPath, currentSource,
        isSelectionMode, selectedItems, renameTarget,
        onPdfClick, onUpClick, onSourceChange,
        onToggleSelectionMode, onClearSelection, onToggleSelect,
        onOpenRename, onCloseRename, onRenameItem, onRefresh,
        onBulkSelect,
    } = useLibraryContext();

    const [searchText, setSearchText] = useState('');
    const [seriesEditTarget, setSeriesEditTarget] = useState<string | null>(null);
    const dialogs = useDialogToggles<BulkDialogKey>();

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
        recordView, updateAuthors, updateTags, updateGenre, setHidden,
        assignSeries, unassignSeries, reorderSeries,
        allAuthors, allTags, allSeries, allSeriesWithStats, refreshMeta,
    } = useBookMeta(currentSource);
    const { genres, addGenre, removeGenre, reorderGenres } = useGenres(currentSource);
    const { toasts, showToast, dismissToast } = useToast();
    const runAsync = useAsyncToast(showToast);

    const { pinnedBooks, contextualFavorites } = usePinnedBookSets({
        meta, currentPath, seriesPins, authorPins, authorFilter, seriesFilter,
    });

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

    const { filteredPdfs } = useLibraryFilter({
        pdfs: sortedPdfs,
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

    const { grouped, displayPdfs, breadcrumbs } = useLibraryDisplay({
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
        bookMeta: { updateAuthors, updateTags, updateGenre, setHidden, assignSeries, reorderSeries },
        addGenre,
        currentGenres: genres,
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

    const { isMixedAuthors, seriesEditFilteredSeries, bulkSeriesFiltered } = useSeriesAuthorFilter({
        meta, selectedItems, getAuthors, currentPath,
        allSeries, allSeriesWithStats, seriesEditTarget,
    });

    const handleSeriesAssign = useCallback(async (params: { title: string; index: number | number[]; id?: string }) => {
        if (!seriesEditTarget) return;
        await runAsync(
            () => assignSeries(currentPath, [seriesEditTarget], params),
            'シリーズ割り当てに失敗しました。',
            { rethrow: true },
        );
    }, [seriesEditTarget, assignSeries, currentPath, runAsync]);

    const handleSeriesUnassign = useCallback(async () => {
        if (!seriesEditTarget) return;
        await runAsync(
            () => unassignSeries(currentPath, [seriesEditTarget]),
            'シリーズ解除に失敗しました。',
            { rethrow: true },
        );
    }, [seriesEditTarget, unassignSeries, currentPath, runAsync]);

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
                onBulkSetAuthor={() => dialogs.open('bulkAuthor')}
                onBulkSetTag={() => dialogs.open('bulkTag')}
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
                renameTarget={renameTarget}
                onCloseRename={onCloseRename}
                onRenameItem={onRenameItem}
                isBulkAuthorOpen={dialogs.isOpen('bulkAuthor')}
                bulkAuthorAllAuthors={allAuthors}
                onCloseBulkAuthor={dialogs.close}
                onBulkApplyAuthors={bulkActions.handleBulkApplyAuthors}
                isBulkTagOpen={dialogs.isOpen('bulkTag')}
                bulkTagInitial={bulkTagInitial}
                onCloseBulkTag={dialogs.close}
                onBulkApplyTags={bulkActions.handleBulkApplyTags}
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
                allSeries={seriesEditFilteredSeries}
                onClose={() => setSeriesEditTarget(null)}
                onAssign={handleSeriesAssign}
                onUnassign={handleSeriesUnassign}
            />

            <ToastContainer toasts={toasts} onDismiss={dismissToast} />
        </>
    );
}
