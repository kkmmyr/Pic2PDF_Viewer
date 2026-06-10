import { useReaderShortcuts } from './useReaderShortcuts';

interface UseReaderInputProps {
    toggleFullscreen: () => void;
    toggleEditMode: () => void;
    openHelp: () => void;
    openSearch: () => void;
    hasNextVolume: boolean;
    hasPrevVolume: boolean;
    onSelectPdf: ((name: string) => void) | undefined;
    onNavigateNextVolume: () => void;
    onNavigatePrevVolume: () => void;
}

/**
 * リーダー画面のキーボード入力層。`useReaderShortcuts` への引数を計算してブリッジする。
 * hasNextVolume / hasPrevVolume + onSelectPdf の AND 判定をここに集約する。
 */
export function useReaderInput({
    toggleFullscreen,
    toggleEditMode,
    openHelp,
    openSearch,
    hasNextVolume,
    hasPrevVolume,
    onSelectPdf,
    onNavigateNextVolume,
    onNavigatePrevVolume,
}: UseReaderInputProps): void {
    useReaderShortcuts({
        isActive: true,
        onToggleFullscreen: toggleFullscreen,
        onToggleEditMode: toggleEditMode,
        onOpenHelp: openHelp,
        onToggleSearch: openSearch,
        onNavigateNextVolume: hasNextVolume && onSelectPdf ? onNavigateNextVolume : null,
        onNavigatePrevVolume: hasPrevVolume && onSelectPdf ? onNavigatePrevVolume : null,
    });
}
