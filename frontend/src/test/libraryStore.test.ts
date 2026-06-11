import { beforeEach, describe, it, expect } from 'vitest';

import { useLibraryStore } from '@/stores/libraryStore';

const resetStore = () =>
    useLibraryStore.setState({
        currentPath: '',
        currentSource: 'doujin',
        isSelectionMode: false,
        selectedItems: new Set(),
        renameTarget: null,
    });

describe('libraryStore', () => {
    beforeEach(() => {
        resetStore();
    });

    describe('selection mode', () => {
        it('初期は isSelectionMode=false / selectedItems 空', () => {
            const s = useLibraryStore.getState();
            expect(s.isSelectionMode).toBe(false);
            expect(s.selectedItems.size).toBe(0);
        });

        it('toggleSelectionMode で on/off', () => {
            useLibraryStore.getState().toggleSelectionMode();
            expect(useLibraryStore.getState().isSelectionMode).toBe(true);
            useLibraryStore.getState().toggleSelectionMode();
            expect(useLibraryStore.getState().isSelectionMode).toBe(false);
        });

        it('toggleSelectionMode で off にしたとき選択もクリアされる', () => {
            useLibraryStore.getState().toggleSelectionMode();
            useLibraryStore.getState().toggleSelectItem('a.pdf');
            expect(useLibraryStore.getState().selectedItems.has('a.pdf')).toBe(true);
            useLibraryStore.getState().toggleSelectionMode();
            expect(useLibraryStore.getState().selectedItems.size).toBe(0);
        });

        it('clearSelection で isSelectionMode=false かつ selectedItems 空', () => {
            useLibraryStore.getState().toggleSelectionMode();
            useLibraryStore.getState().toggleSelectItem('a.pdf');
            useLibraryStore.getState().clearSelection();
            expect(useLibraryStore.getState().isSelectionMode).toBe(false);
            expect(useLibraryStore.getState().selectedItems.size).toBe(0);
        });

        it('toggleSelectItem で追加 → 再呼び出しで削除', () => {
            useLibraryStore.getState().toggleSelectItem('a.pdf');
            expect(useLibraryStore.getState().selectedItems.has('a.pdf')).toBe(true);
            useLibraryStore.getState().toggleSelectItem('a.pdf');
            expect(useLibraryStore.getState().selectedItems.has('a.pdf')).toBe(false);
        });

        it('bulkSelectItems で複数を一括追加', () => {
            useLibraryStore.getState().bulkSelectItems(['a', 'b', 'c'], true);
            const { selectedItems } = useLibraryStore.getState();
            expect(selectedItems.size).toBe(3);
            expect([...selectedItems].sort()).toEqual(['a', 'b', 'c']);
        });

        it('bulkSelectItems で複数を一括解除', () => {
            useLibraryStore.getState().bulkSelectItems(['a', 'b', 'c'], true);
            useLibraryStore.getState().bulkSelectItems(['b'], false);
            expect([...useLibraryStore.getState().selectedItems].sort()).toEqual(['a', 'c']);
        });
    });

    describe('rename dialog', () => {
        it('openRenameDialog で renameTarget が設定される', () => {
            useLibraryStore.getState().openRenameDialog('book.pdf');
            expect(useLibraryStore.getState().renameTarget).toEqual({
                name: 'book.pdf',
                isFolder: false,
            });
        });

        it('openRenameDialog の isFolder=true でフォルダ扱い', () => {
            useLibraryStore.getState().openRenameDialog('subfolder', true);
            expect(useLibraryStore.getState().renameTarget).toEqual({
                name: 'subfolder',
                isFolder: true,
            });
        });

        it('closeRenameDialog で renameTarget=null', () => {
            useLibraryStore.getState().openRenameDialog('book.pdf');
            useLibraryStore.getState().closeRenameDialog();
            expect(useLibraryStore.getState().renameTarget).toBeNull();
        });
    });
});
