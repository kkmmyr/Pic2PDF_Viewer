import { useEffect } from 'react';

interface UseReaderShortcutsProps {
    /** リーダーが表示中のときだけショートカットを有効化する */
    isActive: boolean;
    onToggleFullscreen: () => void;
    onToggleEditMode: () => void;
    onOpenHelp: () => void;
    onToggleSearch: () => void;
    /** 次巻あり時に渡す。null なら ↓ キーは無効 */
    onNavigateNextVolume: (() => void) | null;
    /** 前巻あり時に渡す。null なら ↑ キーは無効 */
    onNavigatePrevVolume: (() => void) | null;
}

/**
 * 入力中（input / textarea / contentEditable）かどうか。
 * 入力欄内の文字キーはショートカットとして扱わない。
 */
function isTypingInForm(target: EventTarget | null): boolean {
    if (!(target instanceof HTMLElement)) return false;
    const tag = target.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true;
    if (target.isContentEditable) return true;
    return false;
}

/**
 * リーダー画面のキーボードショートカットを集約するフック。
 *
 * 矢印キーは `useReaderNavigation` が別途管理するため、ここでは扱わない。
 */
export function useReaderShortcuts({
    isActive,
    onToggleFullscreen,
    onToggleEditMode,
    onOpenHelp,
    onToggleSearch,
    onNavigateNextVolume,
    onNavigatePrevVolume,
}: UseReaderShortcutsProps): void {
    useEffect(() => {
        if (!isActive) return;

        const handleKeyDown = (e: KeyboardEvent) => {
            // Ctrl+F / Cmd+F: 検索（入力欄内でも常に有効）
            if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
                e.preventDefault();
                onToggleSearch();
                return;
            }

            // 入力中・修飾キー付きはブラウザ操作を尊重
            if (isTypingInForm(e.target)) return;
            if (e.ctrlKey || e.metaKey || e.altKey) return;

            switch (e.key) {
                case 'f':
                    e.preventDefault();
                    onToggleFullscreen();
                    break;
                case 'e':
                    e.preventDefault();
                    onToggleEditMode();
                    break;
                case '?':
                    e.preventDefault();
                    onOpenHelp();
                    break;
                case 'ArrowDown':
                    if (onNavigateNextVolume) {
                        e.preventDefault();
                        onNavigateNextVolume();
                    }
                    break;
                case 'ArrowUp':
                    if (onNavigatePrevVolume) {
                        e.preventDefault();
                        onNavigatePrevVolume();
                    }
                    break;
            }
        };

        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [isActive, onToggleFullscreen, onToggleEditMode, onOpenHelp, onToggleSearch, onNavigateNextVolume, onNavigatePrevVolume]);
}
