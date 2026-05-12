import { renderHook, act } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';

vi.mock('../config/api_client', () => ({
    default: { patch: vi.fn() },
}));

import apiClient from '../config/api_client';
import { useLibraryManagement } from '../hooks/useLibraryManagement';

const mockedPatch = apiClient.patch as ReturnType<typeof vi.fn>;

const renderLM = (onRefresh = vi.fn()) =>
    renderHook(() =>
        useLibraryManagement({
            currentPath: '',
            currentSource: 'doujin',
            onRefresh,
        }),
    );

describe('useLibraryManagement', () => {
    beforeEach(() => {
        mockedPatch.mockReset();
    });

    describe('selection mode', () => {
        it('初期は isSelectionMode=false / selectedItems 空', () => {
            const { result } = renderLM();
            expect(result.current.isSelectionMode).toBe(false);
            expect(result.current.selectedItems.size).toBe(0);
        });

        it('toggleSelectionMode で on/off', () => {
            const { result } = renderLM();
            act(() => result.current.toggleSelectionMode());
            expect(result.current.isSelectionMode).toBe(true);
            act(() => result.current.toggleSelectionMode());
            expect(result.current.isSelectionMode).toBe(false);
        });

        it('toggleSelectionMode で off にしたとき選択もクリアされる', () => {
            const { result } = renderLM();
            act(() => result.current.toggleSelectionMode());
            act(() => result.current.toggleSelectItem('a.pdf'));
            expect(result.current.selectedItems.has('a.pdf')).toBe(true);
            act(() => result.current.toggleSelectionMode());
            expect(result.current.selectedItems.size).toBe(0);
        });

        it('clearSelection で isSelectionMode=false かつ selectedItems 空', () => {
            const { result } = renderLM();
            act(() => result.current.toggleSelectionMode());
            act(() => result.current.toggleSelectItem('a.pdf'));
            act(() => result.current.clearSelection());
            expect(result.current.isSelectionMode).toBe(false);
            expect(result.current.selectedItems.size).toBe(0);
        });

        it('toggleSelectItem で追加 → 再呼び出しで削除', () => {
            const { result } = renderLM();
            act(() => result.current.toggleSelectItem('a.pdf'));
            expect(result.current.selectedItems.has('a.pdf')).toBe(true);
            act(() => result.current.toggleSelectItem('a.pdf'));
            expect(result.current.selectedItems.has('a.pdf')).toBe(false);
        });

        it('bulkSelectItems で複数を一括追加', () => {
            const { result } = renderLM();
            act(() => result.current.bulkSelectItems(['a', 'b', 'c'], true));
            expect(result.current.selectedItems.size).toBe(3);
            expect([...result.current.selectedItems].sort()).toEqual(['a', 'b', 'c']);
        });

        it('bulkSelectItems で複数を一括解除', () => {
            const { result } = renderLM();
            act(() => result.current.bulkSelectItems(['a', 'b', 'c'], true));
            act(() => result.current.bulkSelectItems(['b'], false));
            expect([...result.current.selectedItems].sort()).toEqual(['a', 'c']);
        });
    });

    describe('rename dialog', () => {
        it('openRenameDialog で renameTarget が設定される', () => {
            const { result } = renderLM();
            act(() => result.current.openRenameDialog('book.pdf'));
            expect(result.current.renameTarget).toEqual({ name: 'book.pdf', isFolder: false });
        });

        it('openRenameDialog の isFolder=true でフォルダ扱い', () => {
            const { result } = renderLM();
            act(() => result.current.openRenameDialog('subfolder', true));
            expect(result.current.renameTarget).toEqual({ name: 'subfolder', isFolder: true });
        });

        it('closeRenameDialog で renameTarget=null', () => {
            const { result } = renderLM();
            act(() => result.current.openRenameDialog('book.pdf'));
            act(() => result.current.closeRenameDialog());
            expect(result.current.renameTarget).toBeNull();
        });

        it('handleRename: renameTarget があるとき PATCH /api/rename を呼び renameTarget をクリアし onRefresh', async () => {
            const onRefresh = vi.fn();
            mockedPatch.mockResolvedValue(undefined);

            const { result } = renderHook(() =>
                useLibraryManagement({
                    currentPath: 'sub',
                    currentSource: 'comic',
                    onRefresh,
                }),
            );

            act(() => result.current.openRenameDialog('old.pdf'));

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
            expect(result.current.renameTarget).toBeNull();
            expect(onRefresh).toHaveBeenCalledTimes(1);
        });

        it('handleRename: renameTarget が null のとき PATCH を呼ばない', async () => {
            const onRefresh = vi.fn();
            const { result } = renderLM(onRefresh);

            await act(async () => {
                await result.current.handleRename('whatever');
            });

            expect(mockedPatch).not.toHaveBeenCalled();
            expect(onRefresh).not.toHaveBeenCalled();
        });

        it('handleRename: フォルダリネームで is_folder=true が body に乗る', async () => {
            mockedPatch.mockResolvedValue(undefined);
            const { result } = renderLM();

            act(() => result.current.openRenameDialog('subfolder', true));
            await act(async () => {
                await result.current.handleRename('newfolder');
            });

            expect(mockedPatch.mock.calls[0][1].is_folder).toBe(true);
        });
    });
});
