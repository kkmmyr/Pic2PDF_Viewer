import { renderHook, act } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';

vi.mock('../config/api_client', () => ({
    default: { post: vi.fn() },
}));

import apiClient from '../config/api_client';
import { useEditMode } from '../hooks/useEditMode';

const mockedPost = apiClient.post as ReturnType<typeof vi.fn>;

const renderEM = (overrides: Partial<Parameters<typeof useEditMode>[0]> = {}) => {
    const props = {
        selectedPdf: 'book.pdf',
        currentPath: '',
        currentSource: 'generated' as const,
        pageNumber: 1,
        setPageNumber: vi.fn(),
        onPdfUpdated: vi.fn(),
        bumpPdfVersion: vi.fn(),
        showError: vi.fn(),
        ...overrides,
    };
    return { props, ...renderHook(() => useEditMode(props)) };
};

describe('useEditMode', () => {
    beforeEach(() => {
        mockedPost.mockReset();
    });

    it('初期状態は isEditMode=false / selectedPages 空 / pendingDeleteCount=0', () => {
        const { result } = renderEM();
        expect(result.current.isEditMode).toBe(false);
        expect(result.current.selectedPages.size).toBe(0);
        expect(result.current.pendingDeleteCount).toBe(0);
    });

    it('toggleEditMode で on/off + 選択ページもリセット', () => {
        const { result } = renderEM();
        act(() =>
            result.current.togglePageSelection(2, {
                stopPropagation: () => {},
            } as React.MouseEvent),
        );
        expect(result.current.selectedPages.has(2)).toBe(true);

        act(() => result.current.toggleEditMode());
        expect(result.current.isEditMode).toBe(true);
        expect(result.current.selectedPages.size).toBe(0); // toggleEditMode で選択もリセット
    });

    it('togglePageSelection で追加 → 再呼び出しで削除（stopPropagation も呼ばれる）', () => {
        const { result } = renderEM();
        const stopPropagation = vi.fn();
        const e = { stopPropagation } as unknown as React.MouseEvent;

        act(() => result.current.togglePageSelection(3, e));
        expect(result.current.selectedPages.has(3)).toBe(true);
        expect(stopPropagation).toHaveBeenCalled();

        act(() => result.current.togglePageSelection(3, e));
        expect(result.current.selectedPages.has(3)).toBe(false);
    });

    it('resetEditMode で全状態がリセット', () => {
        const { result } = renderEM();
        act(() =>
            result.current.togglePageSelection(2, {
                stopPropagation: () => {},
            } as React.MouseEvent),
        );
        act(() => result.current.toggleEditMode());

        act(() => result.current.resetEditMode());
        expect(result.current.isEditMode).toBe(false);
        expect(result.current.selectedPages.size).toBe(0);
        expect(result.current.pendingDeleteCount).toBe(0);
    });

    it('requestDeletePages: 選択ページがあると pendingDeleteCount に件数が入る', () => {
        const { result } = renderEM();
        const e = { stopPropagation: () => {} } as React.MouseEvent;
        act(() => result.current.togglePageSelection(1, e));
        act(() => result.current.togglePageSelection(2, e));

        act(() => result.current.requestDeletePages());
        expect(result.current.pendingDeleteCount).toBe(2);
    });

    it('requestDeletePages: 選択ページが空なら何もしない', () => {
        const { result } = renderEM();
        act(() => result.current.requestDeletePages());
        expect(result.current.pendingDeleteCount).toBe(0);
    });

    it('cancelDeletePages で pendingDeleteCount=0 に戻る', () => {
        const { result } = renderEM();
        const e = { stopPropagation: () => {} } as React.MouseEvent;
        act(() => result.current.togglePageSelection(1, e));
        act(() => result.current.requestDeletePages());

        act(() => result.current.cancelDeletePages());
        expect(result.current.pendingDeleteCount).toBe(0);
    });

    it('confirmDeletePages: API 成功で 1-indexed → 0-indexed 変換し POST、selectedPages がリセット', async () => {
        mockedPost.mockResolvedValue({ message: 'ok', total_pages: 8 });
        const onPdfUpdated = vi.fn();
        const bumpPdfVersion = vi.fn();
        const { result } = renderEM({ onPdfUpdated, bumpPdfVersion });

        const e = { stopPropagation: () => {} } as React.MouseEvent;
        act(() => result.current.togglePageSelection(1, e));
        act(() => result.current.togglePageSelection(3, e));

        await act(async () => {
            await result.current.confirmDeletePages();
        });

        const [_url, body] = mockedPost.mock.calls[0];
        expect((body as { page_indices: number[] }).page_indices.sort()).toEqual([0, 2]);
        expect(result.current.isEditMode).toBe(false);
        expect(result.current.selectedPages.size).toBe(0);
        expect(onPdfUpdated).toHaveBeenCalled();
        expect(bumpPdfVersion).toHaveBeenCalled();
    });

    it('confirmDeletePages: 削除後 pageNumber > total_pages の場合は補正', async () => {
        mockedPost.mockResolvedValue({ message: 'ok', total_pages: 5 });
        const setPageNumber = vi.fn();
        const { result } = renderEM({ pageNumber: 10, setPageNumber });

        const e = { stopPropagation: () => {} } as React.MouseEvent;
        act(() => result.current.togglePageSelection(1, e));

        await act(async () => {
            await result.current.confirmDeletePages();
        });

        expect(setPageNumber).toHaveBeenCalledWith(5);
    });

    it('confirmDeletePages: API 失敗で showError が呼ばれる', async () => {
        mockedPost.mockRejectedValue(new Error('削除失敗'));
        const showError = vi.fn();
        const { result } = renderEM({ showError });

        const e = { stopPropagation: () => {} } as React.MouseEvent;
        act(() => result.current.togglePageSelection(1, e));

        await act(async () => {
            await result.current.confirmDeletePages();
        });

        expect(showError).toHaveBeenCalledWith('削除失敗');
        expect(result.current.pendingDeleteCount).toBe(0);
    });

    it('confirmDeletePages: 選択ページが空なら API を呼ばず pendingDeleteCount=0', async () => {
        const { result } = renderEM();
        await act(async () => {
            await result.current.confirmDeletePages();
        });
        expect(mockedPost).not.toHaveBeenCalled();
        expect(result.current.pendingDeleteCount).toBe(0);
    });
});
