import React from 'react';
import { renderHook, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi, describe, it, expect, beforeEach } from 'vitest';

const createWrapper = () => {
    const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    });
    return ({ children }: { children: React.ReactNode }) =>
        React.createElement(QueryClientProvider, { client: queryClient }, children);
};

const mockSetGroupMode = vi.fn();
const mockSetSeriesFilter = vi.fn();
const mockToggleSelectItem = vi.fn();
const mockBulkSelectItems = vi.fn();
const mockToggleSeriesPin = vi.fn();
const mockToggleAuthorPin = vi.fn();
const mockRecordView = vi.fn();
const mockCloseRenameDialog = vi.fn();

const mockMembersByRep = new Map<string, { name: string }[]>();
const mockSelectedItems = new Set<string>();
const mockMeta: Record<string, { series_id?: string; authors?: string[] }> = {};

// handleRename テスト用に変更可能なストア状態
let mockCurrentPath = '';
let mockCurrentSource: 'doujin' | 'comic' | 'novel' = 'doujin';
let mockRenameTarget: { name: string; isFolder: boolean } | null = null;

vi.mock('../stores/libraryStore', () => ({
    useLibraryStore: () => ({
        currentPath: mockCurrentPath,
        currentSource: mockCurrentSource,
        isSelectionMode: false,
        selectedItems: mockSelectedItems,
        renameTarget: mockRenameTarget,
        toggleSelectionMode: vi.fn(),
        clearSelection: vi.fn(),
        toggleSelectItem: mockToggleSelectItem,
        bulkSelectItems: mockBulkSelectItems,
        openRenameDialog: vi.fn(),
        closeRenameDialog: mockCloseRenameDialog,
    }),
}));

vi.mock('../hooks/library/useLibraryPdfs', () => ({
    useLibraryPdfs: () => ({ data: [] }),
    pdfQueryKey: () => ['pdfs'],
}));

vi.mock('../hooks/library/useUrlState', () => ({
    useUrlState: () => ({ selectedPdf: null }),
}));

vi.mock('../hooks', () => ({
    useLibraryPins: () => ({
        seriesPins: {},
        authorPins: {},
        toggleSeriesPin: mockToggleSeriesPin,
        toggleAuthorPin: mockToggleAuthorPin,
    }),
    useSortedPdfs: () => [],
    useBookMeta: () => ({
        meta: mockMeta,
        getAuthors: vi.fn(() => []),
        getSeries: vi.fn(),
        getViewCount: vi.fn(() => 0),
        getLastViewedAt: vi.fn(() => null),
        getReadState: vi.fn(),
        isHidden: vi.fn(() => false),
        recordView: mockRecordView,
        updateAuthors: vi.fn(),
        updateGenre: vi.fn(),
        setHidden: vi.fn(),
        assignSeries: vi.fn(),
        unassignSeries: vi.fn(),
        reorderSeries: vi.fn(),
        allAuthors: [],
        allSeries: [],
        allSeriesWithStats: [],
        refreshMeta: vi.fn(),
    }),
    useLibraryFilter: () => ({ filteredPdfs: [] }),
    useUrlFilters: () => ({
        authorFilter: '',
        seriesFilter: '',
        setAuthorFilter: vi.fn(),
        setSeriesFilter: mockSetSeriesFilter,
        clearAllDrilldown: vi.fn(),
    }),
    useLibrarySettings: () => ({
        sortOrder: 'name' as const,
        setSortOrder: vi.fn(),
        groupMode: 'none' as const,
        setGroupMode: mockSetGroupMode,
        showHidden: false,
        toggleShowHidden: vi.fn(),
        readStateFilter: 'all' as const,
        setReadStateFilter: vi.fn(),
        genreFilter: '',
        setGenreFilter: vi.fn(),
    }),
    useLibraryBulkActions: () => ({
        handleBulkToggleHidden: vi.fn(),
        handleBulkDelete: vi.fn(),
        handleRegenThumbnailBulk: vi.fn(),
        handleBulkApplyAuthors: vi.fn(),
        handleMergePdfs: vi.fn(),
        handleBulkAssignSeries: vi.fn(),
        handleBulkApplyGenre: vi.fn(),
        handleToggleHiddenOne: vi.fn(),
        handleSeriesReorder: vi.fn(),
        bulkSeriesNames: [],
    }),
    useLibraryDisplay: () => ({
        grouped: {
            membersByRepresentativeName: mockMembersByRep,
            badgeByRepresentativeName: new Map(),
        },
        displayPdfs: [],
        breadcrumbs: [],
    }),
    useGenres: () => ({
        genres: [],
        addGenre: vi.fn(),
        removeGenre: vi.fn(),
        reorderGenres: vi.fn(),
    }),
    useScrollMemory: vi.fn(),
    useLibrarySelectionShortcut: vi.fn(),
    useSeriesEditDialog: () => ({
        target: null,
        open: vi.fn(),
        close: vi.fn(),
        assign: vi.fn(),
        unassign: vi.fn(),
    }),
}));

vi.mock('../hooks/library/usePinnedBookSets', () => ({
    usePinnedBookSets: () => ({ pinnedBooks: new Set(), contextualFavorites: new Set() }),
}));

vi.mock('../hooks/library/useSeriesAuthorFilter', () => ({
    useSeriesAuthorFilter: () => ({
        isMixedAuthors: false,
        seriesEditFilteredSeries: [],
        bulkSeriesFiltered: [],
    }),
}));

vi.mock('../hooks/library/useDialogToggles', () => ({
    useDialogToggles: () => ({ isOpen: vi.fn(() => false), open: vi.fn(), close: vi.fn() }),
}));

vi.mock('../hooks/useAsyncToast', () => ({
    useAsyncToast: () => vi.fn(),
}));

vi.mock('../config/api_client', () => ({ default: { post: vi.fn(), patch: vi.fn() } }));
vi.mock('../config/api', () => ({
    API_ENDPOINTS: { REGENERATE_THUMBNAIL: '/api/thumb', RENAME: '/api/rename' },
}));
vi.mock('../utils/authors', () => ({ authorsKey: (a: string[]) => a.join('\n') }));

import apiClient from '@/config/api_client';
import { useLibraryPanel } from '@/hooks/library/useLibraryPanel';

const mockedPatch = apiClient.patch as ReturnType<typeof vi.fn>;

describe('useLibraryPanel', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        mockMembersByRep.clear();
        mockSelectedItems.clear();
        Object.keys(mockMeta).forEach((k) => delete mockMeta[k]);
        mockCurrentPath = '';
        mockCurrentSource = 'doujin';
        mockRenameTarget = null;
    });

    it('スモークテスト: hook が正常にレンダーされる', () => {
        const { result } = renderHook(() => useLibraryPanel(vi.fn()), { wrapper: createWrapper() });
        expect(result.current.displayPdfs).toEqual([]);
        expect(result.current.searchText).toBe('');
    });

    it('handleGroupModeChange: setGroupMode と seriesFilter クリアを同時に呼ぶ', () => {
        const { result } = renderHook(() => useLibraryPanel(vi.fn()), { wrapper: createWrapper() });
        act(() => {
            result.current.handleGroupModeChange('series');
        });
        expect(mockSetGroupMode).toHaveBeenCalledWith('series');
        expect(mockSetSeriesFilter).toHaveBeenCalledWith('');
    });

    it('handleToggleSelect: 集約カード（members あり）は bulkSelectItems を呼ぶ', () => {
        mockMembersByRep.set('book-a', [{ name: 'vol1' }, { name: 'vol2' }]);
        const { result } = renderHook(() => useLibraryPanel(vi.fn()), { wrapper: createWrapper() });
        act(() => {
            result.current.handleToggleSelect('book-a');
        });
        expect(mockBulkSelectItems).toHaveBeenCalledWith(['vol1', 'vol2'], true);
        expect(mockToggleSelectItem).not.toHaveBeenCalled();
    });

    it('handleToggleSelect: 集約カード（全選択済み）は bulkSelectItems(false) を呼ぶ', () => {
        mockMembersByRep.set('book-a', [{ name: 'vol1' }, { name: 'vol2' }]);
        mockSelectedItems.add('vol1');
        mockSelectedItems.add('vol2');
        const { result } = renderHook(() => useLibraryPanel(vi.fn()), { wrapper: createWrapper() });
        act(() => {
            result.current.handleToggleSelect('book-a');
        });
        expect(mockBulkSelectItems).toHaveBeenCalledWith(['vol1', 'vol2'], false);
    });

    it('handleToggleSelect: 非集約アイテムは toggleSelectItem を呼ぶ', () => {
        const { result } = renderHook(() => useLibraryPanel(vi.fn()), { wrapper: createWrapper() });
        act(() => {
            result.current.handleToggleSelect('single-book');
        });
        expect(mockToggleSelectItem).toHaveBeenCalledWith('single-book');
        expect(mockBulkSelectItems).not.toHaveBeenCalled();
    });

    it('handlePdfClick: recordView を呼んだあと onPdfClick を呼ぶ', () => {
        const onPdfClick = vi.fn();
        const { result } = renderHook(() => useLibraryPanel(onPdfClick), {
            wrapper: createWrapper(),
        });
        act(() => {
            result.current.handlePdfClick('test.pdf');
        });
        expect(mockRecordView).toHaveBeenCalledWith('', 'test.pdf');
        expect(onPdfClick).toHaveBeenCalledWith('test.pdf');
    });

    describe('handleRename', () => {
        it('renameTarget が null のとき PATCH を呼ばない', async () => {
            // mockRenameTarget = null (beforeEach でリセット済み)
            const { result } = renderHook(() => useLibraryPanel(vi.fn()), {
                wrapper: createWrapper(),
            });
            await act(async () => {
                await result.current.handleRename('new.pdf');
            });
            expect(mockedPatch).not.toHaveBeenCalled();
        });

        it('renameTarget があるとき PATCH /api/rename を正しいパラメータで呼ぶ', async () => {
            mockedPatch.mockResolvedValue(undefined);
            mockCurrentPath = 'sub';
            mockCurrentSource = 'comic';
            mockRenameTarget = { name: 'old.pdf', isFolder: false };

            const { result } = renderHook(() => useLibraryPanel(vi.fn()), {
                wrapper: createWrapper(),
            });
            await act(async () => {
                await result.current.handleRename('new.pdf');
            });

            expect(mockedPatch).toHaveBeenCalledWith('/api/rename', {
                path: 'sub',
                old_name: 'old.pdf',
                new_name: 'new.pdf',
                source: 'comic',
                is_folder: false,
            });
        });

        it('フォルダリネームで is_folder=true が body に乗る', async () => {
            mockedPatch.mockResolvedValue(undefined);
            mockRenameTarget = { name: 'subfolder', isFolder: true };

            const { result } = renderHook(() => useLibraryPanel(vi.fn()), {
                wrapper: createWrapper(),
            });
            await act(async () => {
                await result.current.handleRename('newfolder');
            });

            expect(mockedPatch.mock.calls[0][1].is_folder).toBe(true);
        });

        it('PATCH 成功後に closeRenameDialog が呼ばれる', async () => {
            mockedPatch.mockResolvedValue(undefined);
            mockRenameTarget = { name: 'old.pdf', isFolder: false };

            const { result } = renderHook(() => useLibraryPanel(vi.fn()), {
                wrapper: createWrapper(),
            });
            await act(async () => {
                await result.current.handleRename('new.pdf');
            });

            expect(mockCloseRenameDialog).toHaveBeenCalledTimes(1);
        });
    });
});
