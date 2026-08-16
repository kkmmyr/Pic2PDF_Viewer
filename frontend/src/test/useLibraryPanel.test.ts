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
const mockRefetchPdfs = vi.fn();
const mockRefreshMeta = vi.fn();
const mockRefetchGenres = vi.fn();
const mockClearAllDrilldown = vi.fn();
const mockSetReadStateFilter = vi.fn();
const mockSetGenreFilter = vi.fn();
const mockToggleShowHidden = vi.fn();
const mockIsHidden = vi.fn(() => false);

const mockMembersByRep = new Map<string, { name: string }[]>();
const mockSelectedItems = new Set<string>();
const mockMeta: Record<string, { series_id?: string; authors?: string[] }> = {};

// handleRename テスト用に変更可能なストア状態
let mockCurrentPath = '';
let mockCurrentSource: 'doujin' | 'comic' | 'novel' = 'doujin';
let mockRenameTarget: { name: string; isFolder: boolean } | null = null;
let mockPdfsError = false;
let mockMetaError = false;
let mockGenresError = false;
let mockPdfs: { name: string; thumbnail: null; created_at: number }[] = [];
let mockFilteredPdfs: { name: string; thumbnail: null; created_at: number }[] = [];
let mockAuthorFilter = '';
let mockSeriesFilter = '';
let mockReadStateFilter = '';
let mockGenreFilter = '';
let mockShowHidden = false;

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
    useLibraryPdfs: () => ({
        data: mockPdfs,
        isLoading: false,
        isError: mockPdfsError,
        refetch: mockRefetchPdfs,
    }),
    pdfQueryKey: () => ['pdfs'],
}));

vi.mock('../hooks/library/useUrlState', () => ({
    useUrlState: () => ({ selectedPdf: null }),
}));

vi.mock('../hooks/library/useLibraryPins', () => ({
    useLibraryPins: () => ({
        seriesPins: {},
        authorPins: {},
        toggleSeriesPin: mockToggleSeriesPin,
        toggleAuthorPin: mockToggleAuthorPin,
    }),
}));

vi.mock('../hooks/library/useSortedPdfs', () => ({
    useSortedPdfs: () => [],
}));

vi.mock('../hooks/library/useBookMeta', () => ({
    useBookMeta: () => ({
        meta: mockMeta,
        getAuthors: vi.fn(() => []),
        getSeries: vi.fn(),
        getViewCount: vi.fn(() => 0),
        getLastViewedAt: vi.fn(() => null),
        getReadState: vi.fn(),
        isHidden: mockIsHidden,
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
        refreshMeta: mockRefreshMeta,
        isError: mockMetaError,
    }),
}));

vi.mock('../hooks/library/useLibraryFilter', () => ({
    useLibraryFilter: () => ({ filteredPdfs: mockFilteredPdfs }),
}));

vi.mock('../hooks/library/useUrlFilters', () => ({
    useUrlFilters: () => ({
        authorFilter: mockAuthorFilter,
        seriesFilter: mockSeriesFilter,
        setAuthorFilter: vi.fn(),
        setSeriesFilter: mockSetSeriesFilter,
        clearAllDrilldown: mockClearAllDrilldown,
    }),
}));

vi.mock('../hooks/library/useLibrarySettings', () => ({
    useLibrarySettings: () => ({
        sortOrder: 'name' as const,
        setSortOrder: vi.fn(),
        groupMode: 'none' as const,
        setGroupMode: mockSetGroupMode,
        showHidden: mockShowHidden,
        toggleShowHidden: mockToggleShowHidden,
        readStateFilter: mockReadStateFilter,
        setReadStateFilter: mockSetReadStateFilter,
        genreFilter: mockGenreFilter,
        setGenreFilter: mockSetGenreFilter,
    }),
}));

vi.mock('../hooks/library/useLibraryBulkActions', () => ({
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
}));

vi.mock('../hooks/library/useLibraryDisplay', () => ({
    useLibraryDisplay: () => ({
        grouped: {
            membersByRepresentativeName: mockMembersByRep,
            badgeByRepresentativeName: new Map(),
        },
        displayPdfs: [],
        breadcrumbs: [],
    }),
}));

vi.mock('../hooks/library/useGenres', () => ({
    useGenres: () => ({
        genres: [],
        addGenre: vi.fn(),
        removeGenre: vi.fn(),
        reorderGenres: vi.fn(),
        isError: mockGenresError,
        refetch: mockRefetchGenres,
    }),
}));

vi.mock('../hooks/library/useScrollMemory', () => ({
    useScrollMemory: vi.fn(),
}));

vi.mock('../hooks/library/useLibrarySelectionShortcut', () => ({
    useLibrarySelectionShortcut: vi.fn(),
}));

vi.mock('../hooks/library/useSeriesEditDialog', () => ({
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
        mockPdfsError = false;
        mockMetaError = false;
        mockGenresError = false;
        mockPdfs = [];
        mockFilteredPdfs = [];
        mockAuthorFilter = '';
        mockSeriesFilter = '';
        mockReadStateFilter = '';
        mockGenreFilter = '';
        mockShowHidden = false;
        mockIsHidden.mockReturnValue(false);
    });

    it('スモークテスト: hook が正常にレンダーされる', () => {
        const { result } = renderHook(() => useLibraryPanel(vi.fn()), { wrapper: createWrapper() });
        expect(result.current.displayPdfs).toEqual([]);
        expect(result.current.searchText).toBe('');
    });

    it('PDF一覧取得エラーを空状態と分離し、再試行で全データを再取得する', async () => {
        mockPdfsError = true;
        mockRefetchPdfs.mockResolvedValue(undefined);
        mockRefreshMeta.mockResolvedValue(undefined);
        mockRefetchGenres.mockResolvedValue(undefined);
        const { result } = renderHook(() => useLibraryPanel(vi.fn()), {
            wrapper: createWrapper(),
        });

        expect(result.current.isPdfsError).toBe(true);
        expect(result.current.hasSupportingDataError).toBe(false);
        await act(async () => result.current.retryLibraryData());
        expect(mockRefetchPdfs).toHaveBeenCalledTimes(1);
        expect(mockRefreshMeta).toHaveBeenCalledTimes(1);
        expect(mockRefetchGenres).toHaveBeenCalledTimes(1);
    });

    it('メタ情報またはジャンル情報だけの失敗を補助データ警告として公開する', () => {
        mockMetaError = true;
        const { result } = renderHook(() => useLibraryPanel(vi.fn()), {
            wrapper: createWrapper(),
        });

        expect(result.current.isPdfsError).toBe(false);
        expect(result.current.hasSupportingDataError).toBe(true);
    });

    it('PDF一覧と補助情報が同時に失敗した場合は補助データ警告を重ねない', () => {
        mockPdfsError = true;
        mockGenresError = true;
        const { result } = renderHook(() => useLibraryPanel(vi.fn()), {
            wrapper: createWrapper(),
        });

        expect(result.current.isPdfsError).toBe(true);
        expect(result.current.hasSupportingDataError).toBe(false);
    });

    it('clearLibraryFilters は検索・ドリルダウン・読書状態・ジャンルを解除する', () => {
        mockAuthorFilter = '作者A';
        mockSeriesFilter = 'series-a';
        mockReadStateFilter = 'done';
        mockGenreFilter = 'ジャンルA';
        const { result } = renderHook(() => useLibraryPanel(vi.fn()), {
            wrapper: createWrapper(),
        });

        act(() => result.current.setSearchText('検索語'));
        act(() => result.current.clearLibraryFilters());

        expect(result.current.searchText).toBe('');
        expect(mockClearAllDrilldown).toHaveBeenCalledTimes(1);
        expect(mockSetReadStateFilter).toHaveBeenCalledWith('');
        expect(mockSetGenreFilter).toHaveBeenCalledWith('');
        expect(mockToggleShowHidden).not.toHaveBeenCalled();
    });

    it('検索・絞り込み条件数とgrouping前の結果件数を公開する', () => {
        mockPdfs = [
            { name: 'a.pdf', thumbnail: null, created_at: 0 },
            { name: 'b.pdf', thumbnail: null, created_at: 0 },
        ];
        mockFilteredPdfs = [{ name: 'a.pdf', thumbnail: null, created_at: 0 }];
        mockAuthorFilter = '作者A';
        mockReadStateFilter = 'done';
        mockGenreFilter = 'ジャンルA';
        mockShowHidden = true;
        const { result } = renderHook(() => useLibraryPanel(vi.fn()), {
            wrapper: createWrapper(),
        });

        act(() => result.current.setSearchText('検索語'));

        expect(result.current.activeFilterCount).toBe(5);
        expect(result.current.resultBookCount).toBe(1);
        expect(result.current.totalBookCount).toBe(2);
    });

    it('通常表示で全書籍が非表示なら条件解除時に非表示表示へ切り替える', () => {
        mockPdfs = [{ name: 'hidden.pdf', thumbnail: null, created_at: 0 }];
        mockIsHidden.mockReturnValue(true);
        const { result } = renderHook(() => useLibraryPanel(vi.fn()), {
            wrapper: createWrapper(),
        });

        act(() => result.current.clearLibraryFilters());

        expect(mockToggleShowHidden).toHaveBeenCalledTimes(1);
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
