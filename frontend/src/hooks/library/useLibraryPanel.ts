import { useState, useCallback, useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
    useLibraryPins,
    useSortedPdfs,
    useBookMeta,
    useLibraryFilter,
    useUrlFilters,
    useLibrarySettings,
    useLibraryBulkActions,
    useLibraryDisplay,
    useGenres,
    useScrollMemory,
    useLibrarySelectionShortcut,
    useSeriesEditDialog,
} from '..';
import { useAsyncToast } from '@/hooks/useAsyncToast';
import { useUrlState } from './useUrlState';
import { useLibraryPdfs, pdfQueryKey } from './useLibraryPdfs';
import { usePinnedBookSets } from './usePinnedBookSets';
import { useSeriesAuthorFilter } from './useSeriesAuthorFilter';
import { useDialogToggles } from './useDialogToggles';
import { useLibraryStore } from '@/stores/libraryStore';
import { API_ENDPOINTS } from '@/config/api';
import { authorsKey } from '@/utils/authors';
import apiClient from '@/config/api_client';

type BulkDialogKey = 'bulkAuthor' | 'merge' | 'bulkSeries' | 'bulkGenre';

export function useLibraryPanel(onPdfClick: (name: string) => void) {
    const queryClient = useQueryClient();

    const {
        currentPath,
        currentSource,
        isSelectionMode,
        selectedItems,
        renameTarget,
        toggleSelectionMode,
        clearSelection,
        toggleSelectItem,
        bulkSelectItems,
        openRenameDialog,
        closeRenameDialog,
        handleRename: storeHandleRename,
    } = useLibraryStore();

    const { data: pdfs = [] } = useLibraryPdfs(currentPath, currentSource);

    const invalidatePdfs = useCallback(() => {
        void queryClient.invalidateQueries({ queryKey: pdfQueryKey(currentPath, currentSource) });
    }, [queryClient, currentPath, currentSource]);

    const handleRename = useCallback(
        async (newName: string) => {
            await storeHandleRename(newName);
            invalidatePdfs();
        },
        [storeHandleRename, invalidatePdfs],
    );

    const { selectedPdf } = useUrlState();

    const [searchText, setSearchText] = useState('');
    const dialogs = useDialogToggles<BulkDialogKey>();

    const { authorFilter, seriesFilter, setAuthorFilter, setSeriesFilter, clearAllDrilldown } =
        useUrlFilters();

    const {
        sortOrder,
        setSortOrder,
        groupMode,
        setGroupMode,
        showHidden,
        toggleShowHidden,
        readStateFilter,
        setReadStateFilter,
        genreFilter,
        setGenreFilter,
    } = useLibrarySettings(currentSource);

    // パスまたはソース変更時に検索テキストをリセット。
    // author/series は URL 同期されており、useUrlState の navigate
    // メソッドが setSearchParams({ path, source }) で全置換するため自動クリアされる。
    useEffect(() => {
        setSearchText('');
    }, [currentPath, currentSource]);

    useLibrarySelectionShortcut(selectedPdf, toggleSelectionMode);

    const handleGroupModeChange = useCallback(
        (mode: typeof groupMode) => {
            setGroupMode(mode);
            // モード切替時にドリルダウン中のシリーズフィルターは解除（一覧の意味が変わるため）
            setSeriesFilter('');
        },
        [setGroupMode, setSeriesFilter],
    );

    const { seriesPins, authorPins, toggleSeriesPin, toggleAuthorPin } =
        useLibraryPins(currentSource);
    const {
        meta,
        getAuthors,
        getSeries,
        getViewCount,
        getLastViewedAt,
        getReadState,
        isHidden,
        recordView,
        updateAuthors,
        updateGenre,
        setHidden,
        assignSeries,
        unassignSeries,
        reorderSeries,
        allAuthors,
        allSeries,
        allSeriesWithStats,
        refreshMeta,
    } = useBookMeta(currentSource);
    const { genres, addGenre, removeGenre, reorderGenres } = useGenres(currentSource);
    const runAsync = useAsyncToast();

    const { pinnedBooks, contextualFavorites } = usePinnedBookSets({
        meta,
        currentPath,
        seriesPins,
        authorPins,
        authorFilter,
        seriesFilter,
    });

    // favorites_first ソート用 favorites: ドリルダウン中は文脈別ピン、トップ階層は両ピン混在。
    // 星の表示（contextualFavorites）と並び順の意味を一致させる。
    const sortFavorites = seriesFilter || authorFilter ? contextualFavorites : pinnedBooks;
    const sortedPdfs = useSortedPdfs(
        pdfs,
        sortOrder,
        sortFavorites,
        (name) => getViewCount(currentPath, name),
        (name) => getLastViewedAt(currentPath, name),
    );

    // 現在の URL キー。useScrollMemory に渡してスクロール位置を URL 単位で記憶。
    const urlKey = `${currentPath}|${currentSource}|${authorFilter}|${seriesFilter}|${selectedPdf ?? ''}`;
    useScrollMemory(urlKey);

    const handlePdfClick = useCallback(
        (name: string) => {
            recordView(currentPath, name);
            onPdfClick(name);
        },
        [recordView, currentPath, onPdfClick],
    );

    const handleRegenThumb = useCallback(
        async (name: string) => {
            await apiClient.post(API_ENDPOINTS.REGENERATE_THUMBNAIL, {
                path: currentPath,
                name,
                source: currentSource,
            });
            invalidatePdfs();
        },
        [currentPath, currentSource, invalidatePdfs],
    );

    const { filteredPdfs } = useLibraryFilter({
        pdfs: sortedPdfs,
        searchText,
        authorFilter,
        seriesFilter,
        showHidden,
        readStateFilter,
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
        currentPath,
        currentSource,
        selectedItems,
        showHidden,
        seriesFilter,
        onClearSelection: clearSelection,
        onRefresh: invalidatePdfs,
        bookMeta: {
            updateAuthors,
            updateGenre,
            setHidden,
            assignSeries,
            reorderSeries,
        },
        addGenre,
        currentGenres: genres,
    });

    // seriesFilter 中 → シリーズ代表巻ピン、authorFilter 中 → 作者代表カードピン
    const handleTogglePin = useCallback(
        (name: string) => {
            const key = currentPath ? `${currentPath}/${name}` : name;
            const entry = meta[key];
            if (!entry) return;
            if (seriesFilter) {
                if (entry.series_id) toggleSeriesPin(entry.series_id, name);
            } else if (authorFilter) {
                if (entry.authors?.length) toggleAuthorPin(authorsKey(entry.authors), name);
            }
        },
        [currentPath, meta, seriesFilter, authorFilter, toggleSeriesPin, toggleAuthorPin],
    );

    // 集約カードをチェックしたときは全メンバーを一括選択/解除する
    const handleToggleSelect = useCallback(
        (name: string) => {
            const members = grouped.membersByRepresentativeName.get(name);
            if (members && members.length > 0) {
                const allSelected = members.every((m) => selectedItems.has(m.name));
                bulkSelectItems(
                    members.map((m) => m.name),
                    !allSelected,
                );
            } else {
                toggleSelectItem(name);
            }
        },
        [grouped.membersByRepresentativeName, selectedItems, bulkSelectItems, toggleSelectItem],
    );

    const seriesEdit = useSeriesEditDialog({
        currentPath,
        assignSeries,
        unassignSeries,
        runAsync,
    });

    const { isMixedAuthors, seriesEditFilteredSeries, bulkSeriesFiltered } = useSeriesAuthorFilter({
        meta,
        selectedItems,
        getAuthors,
        currentPath,
        allSeries,
        allSeriesWithStats,
        seriesEditTarget: seriesEdit.target,
    });

    return {
        // store state
        currentPath,
        currentSource,
        isSelectionMode,
        selectedItems,
        renameTarget,
        openRenameDialog,
        closeRenameDialog,
        handleRename,
        toggleSelectionMode,
        // search
        searchText,
        setSearchText,
        // dialogs
        dialogs,
        // filters
        authorFilter,
        seriesFilter,
        setAuthorFilter,
        setSeriesFilter,
        // settings
        sortOrder,
        setSortOrder,
        groupMode,
        showHidden,
        toggleShowHidden,
        readStateFilter,
        setReadStateFilter,
        genreFilter,
        setGenreFilter,
        // handlers
        handleGroupModeChange,
        handlePdfClick,
        handleRegenThumb,
        handleTogglePin,
        handleToggleSelect,
        // meta
        meta,
        getAuthors,
        getSeries,
        getReadState,
        // 将来 PdfGrid 内で個別判定する用に export 済（現状は filter 段階で除外）
        isHidden,
        allAuthors,
        refreshMeta,
        // genres
        genres,
        addGenre,
        removeGenre,
        reorderGenres,
        // display
        grouped,
        displayPdfs,
        breadcrumbs,
        contextualFavorites,
        // bulk
        bulkActions,
        // series edit
        seriesEdit,
        seriesEditFilteredSeries,
        bulkSeriesFiltered,
        isMixedAuthors,
    };
}
