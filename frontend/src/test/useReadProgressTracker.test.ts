import { renderHook, act } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { useReadProgressTracker } from '../hooks/reader/useReadProgressTracker';

describe('useReadProgressTracker', () => {
    const mockGetReadState = vi.fn();
    const mockSetReadState = vi.fn();

    const defaultProps = {
        selectedPdf: 'book.pdf',
        currentPath: '/path',
        isAtLastSpread: false,
        getReadState: mockGetReadState,
        setReadState: mockSetReadState,
    };

    beforeEach(() => {
        mockGetReadState.mockReset();
        mockSetReadState.mockReset();
        mockSetReadState.mockResolvedValue(undefined);
        mockGetReadState.mockReturnValue(undefined);
    });

    it('isAtLastSpread=false では setReadState を呼ばない', () => {
        renderHook(() => useReadProgressTracker({ ...defaultProps, isAtLastSpread: false }));
        expect(mockSetReadState).not.toHaveBeenCalled();
    });

    it('isAtLastSpread=true かつ未読で setReadState が呼ばれる', async () => {
        mockGetReadState.mockReturnValue(undefined);
        mockSetReadState.mockResolvedValue(undefined);
        const { rerender } = renderHook(
            (props) => useReadProgressTracker(props),
            { initialProps: { ...defaultProps, isAtLastSpread: false } },
        );
        await act(async () => {
            rerender({ ...defaultProps, isAtLastSpread: true });
        });
        expect(mockSetReadState).toHaveBeenCalledWith('/path', ['book.pdf'], 'done');
    });

    it('既に read_state=done の場合は setReadState を呼ばない', async () => {
        mockGetReadState.mockReturnValue('done');
        const { rerender } = renderHook(
            (props) => useReadProgressTracker(props),
            { initialProps: { ...defaultProps, isAtLastSpread: false } },
        );
        await act(async () => {
            rerender({ ...defaultProps, isAtLastSpread: true });
        });
        expect(mockSetReadState).not.toHaveBeenCalled();
    });

    it('同じ書籍で連続して isAtLastSpread=true になっても 2 回目は呼ばれない', async () => {
        mockGetReadState.mockReturnValue(undefined);
        const { rerender } = renderHook(
            (props) => useReadProgressTracker(props),
            { initialProps: { ...defaultProps, isAtLastSpread: false } },
        );
        await act(async () => {
            rerender({ ...defaultProps, isAtLastSpread: true });
        });
        await act(async () => {
            rerender({ ...defaultProps, isAtLastSpread: false });
            rerender({ ...defaultProps, isAtLastSpread: true });
        });
        expect(mockSetReadState).toHaveBeenCalledTimes(1);
    });

    it('selectedPdf が変わるとガードがリセットされ次の書籍で再び呼ばれる', async () => {
        mockGetReadState.mockReturnValue(undefined);
        const { rerender } = renderHook(
            (props) => useReadProgressTracker(props),
            { initialProps: { ...defaultProps, isAtLastSpread: false } },
        );
        // 1冊目
        await act(async () => {
            rerender({ ...defaultProps, isAtLastSpread: true });
        });
        // 2冊目に切り替え
        await act(async () => {
            rerender({ ...defaultProps, selectedPdf: 'book2.pdf', isAtLastSpread: false });
        });
        await act(async () => {
            rerender({ ...defaultProps, selectedPdf: 'book2.pdf', isAtLastSpread: true });
        });
        expect(mockSetReadState).toHaveBeenCalledTimes(2);
        expect(mockSetReadState).toHaveBeenLastCalledWith('/path', ['book2.pdf'], 'done');
    });

    it('setReadState が throw した場合はガードが外れて次回リトライ可能', async () => {
        mockGetReadState.mockReturnValue(undefined);
        mockSetReadState.mockRejectedValueOnce(new Error('network error'));
        mockSetReadState.mockResolvedValue(undefined);

        const { rerender } = renderHook(
            (props) => useReadProgressTracker(props),
            { initialProps: { ...defaultProps, isAtLastSpread: false } },
        );
        // 1回目: 失敗（.catch() が doneSentForRef を null に戻す）
        await act(async () => {
            rerender({ ...defaultProps, isAtLastSpread: true });
        });
        // .catch() の microtask を flush
        await act(async () => {
            await Promise.resolve();
        });
        // false → true で再度 effect を起動
        await act(async () => {
            rerender({ ...defaultProps, isAtLastSpread: false });
        });
        await act(async () => {
            rerender({ ...defaultProps, isAtLastSpread: true });
        });
        expect(mockSetReadState).toHaveBeenCalledTimes(2);
    });
});
