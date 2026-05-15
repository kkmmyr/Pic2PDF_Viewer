import { renderHook } from '@testing-library/react';
import { vi, describe, it, expect } from 'vitest';
import { useReaderInput } from '../hooks/useReaderInput';

const setup = (overrides: Partial<Parameters<typeof useReaderInput>[0]> = {}) => {
    const props = {
        toggleFullscreen: vi.fn(),
        toggleEditMode: vi.fn(),
        openHelp: vi.fn(),
        openSearch: vi.fn(),
        hasNextVolume: true,
        hasPrevVolume: true,
        onSelectPdf: vi.fn(),
        onNavigateNextVolume: vi.fn(),
        onNavigatePrevVolume: vi.fn(),
        ...overrides,
    };
    renderHook(() => useReaderInput(props));
    return props;
};

const press = (key: string, options: Partial<KeyboardEventInit> = {}) => {
    window.dispatchEvent(new KeyboardEvent('keydown', { key, ...options }));
};

describe('useReaderInput', () => {
    it('"f" キーで toggleFullscreen が呼ばれる', () => {
        const props = setup();
        press('f');
        expect(props.toggleFullscreen).toHaveBeenCalled();
    });

    it('"e" キーで toggleEditMode が呼ばれる', () => {
        const props = setup();
        press('e');
        expect(props.toggleEditMode).toHaveBeenCalled();
    });

    it('"?" キーで openHelp が呼ばれる', () => {
        const props = setup();
        press('?');
        expect(props.openHelp).toHaveBeenCalled();
    });

    it('Ctrl+F で openSearch が呼ばれる', () => {
        const props = setup();
        press('f', { ctrlKey: true });
        expect(props.openSearch).toHaveBeenCalled();
    });

    it('hasNextVolume=true + onSelectPdf あり → ArrowDown で onNavigateNextVolume が呼ばれる', () => {
        const props = setup({ hasNextVolume: true });
        press('ArrowDown');
        expect(props.onNavigateNextVolume).toHaveBeenCalled();
    });

    it('hasNextVolume=false → ArrowDown で onNavigateNextVolume が呼ばれない', () => {
        const props = setup({ hasNextVolume: false });
        press('ArrowDown');
        expect(props.onNavigateNextVolume).not.toHaveBeenCalled();
    });

    it('onSelectPdf=undefined → ArrowDown で onNavigateNextVolume が呼ばれない', () => {
        const props = setup({ onSelectPdf: undefined });
        press('ArrowDown');
        expect(props.onNavigateNextVolume).not.toHaveBeenCalled();
    });

    it('hasPrevVolume=false → ArrowUp で onNavigatePrevVolume が呼ばれない', () => {
        const props = setup({ hasPrevVolume: false });
        press('ArrowUp');
        expect(props.onNavigatePrevVolume).not.toHaveBeenCalled();
    });
});
