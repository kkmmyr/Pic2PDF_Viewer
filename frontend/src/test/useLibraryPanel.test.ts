import { renderHook, act } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';

const mockSetGroupMode = vi.fn();
const mockSetSeriesFilter = vi.fn();
const mockToggleSelectItem = vi.fn();
const mockBulkSelectItems = vi.fn();
const mockToggleSeriesPin = vi.fn();
const mockToggleAuthorPin = vi.fn();
const mockRecordView = vi.fn();
const mockBumpVersion = vi.fn();

const mockMembersByRep = new Map<string, { name: string }[]>();
const mockSelectedItems = new Set<string>();
const mockMeta: Record<string, { series_id?: string; authors?: string[] }> = {};

vi.mock('../stores/libraryStore', () => ({
    useLibraryStore: () => ({
        pdfs: [],
        currentPath: '',
        currentSource: 'doujin' as const,
        isSelectionMode: false,
        selectedItems: mockSelectedItems,
        renameTarget: null,
        toggleSelectionMode: vi.fn(),
        clearSelection: vi.fn(),
        toggleSelectItem: mockToggleSelectItem,
        bulkSelectItems: mockBulkSelectItems,
        openRenameDialog: vi.fn(),
        closeRenameDialog: vi.fn(),
        handleRename: vi.fn(),
        bumpVersion: mockBumpVersion,
    }),
}));

vi.mock('../hooks/useUrlState', () => ({
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
    useToast: () => ({ toasts: [], showToast: vi.fn(), dismissToast: vi.fn() }),
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

vi.mock('../hooks/usePinnedBookSets', () => ({
    usePinnedBookSets: () => ({ pinnedBooks: new Set(), contextualFavorites: new Set() }),
}));

vi.mock('../hooks/useSeriesAuthorFilter', () => ({
    useSeriesAuthorFilter: () => ({
        isMixedAuthors: false,
        seriesEditFilteredSeries: [],
        bulkSeriesFiltered: [],
    }),
}));

vi.mock('../hooks/useDialogToggles', () => ({
    useDialogToggles: () => ({ isOpen: vi.fn(() => false), open: vi.fn(), close: vi.fn() }),
}));

vi.mock('../hooks/useAsyncToast', () => ({
    useAsyncToast: () => vi.fn(),
}));

vi.mock('../config/api_client', () => ({ default: { post: vi.fn() } }));
vi.mock('../config/api', () => ({ API_ENDPOINTS: { REGENERATE_THUMBNAIL: '/api/thumb' } }));
vi.mock('../utils/authors', () => ({ authorsKey: (a: string[]) => a.join('\n') }));

import { useLibraryPanel } from '../hooks/useLibraryPanel';

describe('useLibraryPanel', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        mockMembersByRep.clear();
        mockSelectedItems.clear();
        Object.keys(mockMeta).forEach((k) => delete mockMeta[k]);
    });

    it('スモークテスト: hook が正常にレンダーされる', () => {
        const { result } = renderHook(() => useLibraryPanel(vi.fn()));
        expect(result.current.displayPdfs).toEqual([]);
        expect(result.current.searchText).toBe('');
    });

    it('handleGroupModeChange: setGroupMode と seriesFilter クリアを同時に呼ぶ', () => {
        const { result } = renderHook(() => useLibraryPanel(vi.fn()));
        act(() => {
            result.current.handleGroupModeChange('series');
        });
        expect(mockSetGroupMode).toHaveBeenCalledWith('series');
        expect(mockSetSeriesFilter).toHaveBeenCalledWith('');
    });

    it('handleToggleSelect: 集約カード（members あり）は bulkSelectItems を呼ぶ', () => {
        mockMembersByRep.set('book-a', [{ name: 'vol1' }, { name: 'vol2' }]);
        const { result } = renderHook(() => useLibraryPanel(vi.fn()));
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
        const { result } = renderHook(() => useLibraryPanel(vi.fn()));
        act(() => {
            result.current.handleToggleSelect('book-a');
        });
        expect(mockBulkSelectItems).toHaveBeenCalledWith(['vol1', 'vol2'], false);
    });

    it('handleToggleSelect: 非集約アイテムは toggleSelectItem を呼ぶ', () => {
        const { result } = renderHook(() => useLibraryPanel(vi.fn()));
        act(() => {
            result.current.handleToggleSelect('single-book');
        });
        expect(mockToggleSelectItem).toHaveBeenCalledWith('single-book');
        expect(mockBulkSelectItems).not.toHaveBeenCalled();
    });

    it('handlePdfClick: recordView を呼んだあと onPdfClick を呼ぶ', () => {
        const onPdfClick = vi.fn();
        const { result } = renderHook(() => useLibraryPanel(onPdfClick));
        act(() => {
            result.current.handlePdfClick('test.pdf');
        });
        expect(mockRecordView).toHaveBeenCalledWith('', 'test.pdf');
        expect(onPdfClick).toHaveBeenCalledWith('test.pdf');
    });
});
