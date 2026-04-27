import { useState, useCallback } from 'react';
import type { SpreadMode } from '../types';

interface UseSpreadModeReturn {
    spreadMode: SpreadMode;
    /** auto モードの自動判定結果（実効的な見開きフラグ） */
    isSpread: boolean;
    /** spreadMode を Auto → Spread → Single → Auto の順に循環させる */
    cycleSpreadMode: () => void;
    /** auto モード時にページサイズから見開きかどうかを判定する */
    handlePageSize: (width: number, height: number) => void;
    /** PDF切り替え時に auto 判定をリセットする */
    resetAutoSpread: () => void;
}

/**
 * リーダーの見開きモード（Auto / Spread / Single）を管理するフック。
 *
 * - Auto モードでは PageRenderer から通知されるページサイズ（縦横比）で
 *   見開きにするかを動的に決定する。横長 → 1ページ、縦長 → 見開き。
 */
export function useSpreadMode(): UseSpreadModeReturn {
    const [spreadMode, setSpreadMode] = useState<SpreadMode>('auto');
    // autoモード時にページサイズから計算した実効値（true=見開き、false=1ページ）
    const [autoIsSpread, setAutoIsSpread] = useState(true);

    const isSpread = spreadMode === 'auto'
        ? autoIsSpread
        : spreadMode === 'spread';

    const cycleSpreadMode = useCallback(() => {
        setSpreadMode(prev =>
            prev === 'auto' ? 'spread' : prev === 'spread' ? 'single' : 'auto'
        );
    }, []);

    const handlePageSize = useCallback((width: number, height: number) => {
        if (spreadMode !== 'auto') return;
        setAutoIsSpread(width <= height);
    }, [spreadMode]);

    const resetAutoSpread = useCallback(() => {
        setAutoIsSpread(true);
    }, []);

    return { spreadMode, isSpread, cycleSpreadMode, handlePageSize, resetAutoSpread };
}
