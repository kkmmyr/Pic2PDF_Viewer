import { useEffect } from 'react';

/**
 * Library 画面で `s` キーを押すと選択モードをトグルする keyboard listener。
 *
 * 無効化条件:
 * - リーダーが開いている (`selectedPdf !== null`)
 * - 入力フォーカス中 (INPUT / TEXTAREA / SELECT / contentEditable)
 * - 修飾キー併用 (Ctrl / Meta / Alt)
 */
export function useLibrarySelectionShortcut(
    selectedPdf: string | null,
    onToggleSelectionMode: () => void,
) {
    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if (selectedPdf !== null) return;
            if (e.key !== 's') return;
            const target = e.target as HTMLElement;
            const tag = target.tagName;
            if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target.isContentEditable) return;
            if (e.ctrlKey || e.metaKey || e.altKey) return;
            e.preventDefault();
            onToggleSelectionMode();
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [selectedPdf, onToggleSelectionMode]);
}
