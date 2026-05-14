import { useCallback } from 'react';

interface VolumeRef {
    name: string;
    index: number;
    title: string;
}

interface UseVolumeNavigationProps {
    nextVolume: VolumeRef | null;
    prevVolume: VolumeRef | null;
    onSelectPdf: ((name: string) => void) | undefined;
    recordView: (path: string, name: string) => void;
    currentPath: string;
}

interface UseVolumeNavigationReturn {
    handleNavigateNextVolume: () => void;
    handleNavigatePrevVolume: () => void;
}

/**
 * シリーズ前後巻への遷移ハンドラ。
 * nextVolume / prevVolume が null のときは何もしない。
 */
export function useVolumeNavigation({
    nextVolume,
    prevVolume,
    onSelectPdf,
    recordView,
    currentPath,
}: UseVolumeNavigationProps): UseVolumeNavigationReturn {
    const handleNavigateNextVolume = useCallback(() => {
        if (!nextVolume || !onSelectPdf) return;
        recordView(currentPath, nextVolume.name);
        onSelectPdf(nextVolume.name);
    }, [nextVolume, onSelectPdf, recordView, currentPath]);

    const handleNavigatePrevVolume = useCallback(() => {
        if (!prevVolume || !onSelectPdf) return;
        recordView(currentPath, prevVolume.name);
        onSelectPdf(prevVolume.name);
    }, [prevVolume, onSelectPdf, recordView, currentPath]);

    return { handleNavigateNextVolume, handleNavigatePrevVolume };
}
