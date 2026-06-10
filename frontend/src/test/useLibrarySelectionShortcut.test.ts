import { renderHook } from '@testing-library/react';
import { vi, describe, it, expect } from 'vitest';
import { useLibrarySelectionShortcut } from '../hooks/library/useLibrarySelectionShortcut';

const press = (key: string, options: Partial<KeyboardEventInit> = {}) => {
    window.dispatchEvent(new KeyboardEvent('keydown', { key, ...options }));
};

describe('useLibrarySelectionShortcut', () => {
    it('selectedPdf=null + s キーで onToggleSelectionMode が呼ばれる', () => {
        const onToggle = vi.fn();
        renderHook(() => useLibrarySelectionShortcut(null, onToggle));
        press('s');
        expect(onToggle).toHaveBeenCalled();
    });

    it('selectedPdf が null でないと s キーが無視される', () => {
        const onToggle = vi.fn();
        renderHook(() => useLibrarySelectionShortcut('book.pdf', onToggle));
        press('s');
        expect(onToggle).not.toHaveBeenCalled();
    });

    it('s 以外のキーは無視', () => {
        const onToggle = vi.fn();
        renderHook(() => useLibrarySelectionShortcut(null, onToggle));
        press('a');
        press('S'); // 大文字
        press('Enter');
        expect(onToggle).not.toHaveBeenCalled();
    });

    it('Ctrl+s は無視', () => {
        const onToggle = vi.fn();
        renderHook(() => useLibrarySelectionShortcut(null, onToggle));
        press('s', { ctrlKey: true });
        expect(onToggle).not.toHaveBeenCalled();
    });

    it('Meta+s（Cmd+s）も無視', () => {
        const onToggle = vi.fn();
        renderHook(() => useLibrarySelectionShortcut(null, onToggle));
        press('s', { metaKey: true });
        expect(onToggle).not.toHaveBeenCalled();
    });

    it('input フォーカス中の s キーは無視される', () => {
        const onToggle = vi.fn();
        renderHook(() => useLibrarySelectionShortcut(null, onToggle));

        const input = document.createElement('input');
        document.body.appendChild(input);
        input.dispatchEvent(new KeyboardEvent('keydown', { key: 's', bubbles: true }));
        expect(onToggle).not.toHaveBeenCalled();
        input.remove();
    });

    it('textarea フォーカス中も無視', () => {
        const onToggle = vi.fn();
        renderHook(() => useLibrarySelectionShortcut(null, onToggle));

        const ta = document.createElement('textarea');
        document.body.appendChild(ta);
        ta.dispatchEvent(new KeyboardEvent('keydown', { key: 's', bubbles: true }));
        expect(onToggle).not.toHaveBeenCalled();
        ta.remove();
    });
});
