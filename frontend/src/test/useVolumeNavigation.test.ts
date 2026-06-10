import { renderHook, act } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { useVolumeNavigation } from '../hooks/reader/useVolumeNavigation';

describe('useVolumeNavigation', () => {
    const mockRecordView = vi.fn();
    const mockOnSelectPdf = vi.fn();

    const nextVolume = { name: 'vol2.pdf', index: 1, title: 'Vol 2' };
    const prevVolume = { name: 'vol0.pdf', index: -1, title: 'Vol 0' };

    const defaultProps = {
        nextVolume,
        prevVolume,
        onSelectPdf: mockOnSelectPdf,
        recordView: mockRecordView,
        currentPath: '/path/vol1.pdf',
    };

    beforeEach(() => { vi.clearAllMocks(); });

    it('handleNavigateNextVolume: nextVolume + onSelectPdf あり → recordView/onSelectPdf が呼ばれる', () => {
        const { result } = renderHook(() => useVolumeNavigation(defaultProps));
        act(() => { result.current.handleNavigateNextVolume(); });
        expect(mockRecordView).toHaveBeenCalledWith('/path/vol1.pdf', 'vol2.pdf');
        expect(mockOnSelectPdf).toHaveBeenCalledWith('vol2.pdf');
    });

    it('handleNavigateNextVolume: nextVolume=null → 何も起きない', () => {
        const { result } = renderHook(() =>
            useVolumeNavigation({ ...defaultProps, nextVolume: null }),
        );
        act(() => { result.current.handleNavigateNextVolume(); });
        expect(mockRecordView).not.toHaveBeenCalled();
        expect(mockOnSelectPdf).not.toHaveBeenCalled();
    });

    it('handleNavigateNextVolume: onSelectPdf=undefined → 何も起きない', () => {
        const { result } = renderHook(() =>
            useVolumeNavigation({ ...defaultProps, onSelectPdf: undefined }),
        );
        act(() => { result.current.handleNavigateNextVolume(); });
        expect(mockRecordView).not.toHaveBeenCalled();
    });

    it('handleNavigatePrevVolume: prevVolume + onSelectPdf あり → recordView/onSelectPdf が呼ばれる', () => {
        const { result } = renderHook(() => useVolumeNavigation(defaultProps));
        act(() => { result.current.handleNavigatePrevVolume(); });
        expect(mockRecordView).toHaveBeenCalledWith('/path/vol1.pdf', 'vol0.pdf');
        expect(mockOnSelectPdf).toHaveBeenCalledWith('vol0.pdf');
    });

    it('handleNavigatePrevVolume: prevVolume=null → 何も起きない', () => {
        const { result } = renderHook(() =>
            useVolumeNavigation({ ...defaultProps, prevVolume: null }),
        );
        act(() => { result.current.handleNavigatePrevVolume(); });
        expect(mockRecordView).not.toHaveBeenCalled();
        expect(mockOnSelectPdf).not.toHaveBeenCalled();
    });

    it('handleNavigatePrevVolume: onSelectPdf=undefined → 何も起きない', () => {
        const { result } = renderHook(() =>
            useVolumeNavigation({ ...defaultProps, onSelectPdf: undefined }),
        );
        act(() => { result.current.handleNavigatePrevVolume(); });
        expect(mockRecordView).not.toHaveBeenCalled();
    });
});
