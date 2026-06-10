import { useState, useCallback } from 'react';
import type { SpreadMode } from '../../types';

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

// 横長判定の閾値。width > height * LANDSCAPE_RATIO_THRESHOLD で見開き原稿とみなす。
// 1.0 ちょうどだと正方形に近いページで判定がバタつくため余裕を持たせている。
const LANDSCAPE_RATIO_THRESHOLD = 1.2;

/**
 * リーダーの見開きモード（Auto / Spread / Single）を管理するフック。
 *
 * - Auto モードでは PageRenderer から通知されるページサイズ（縦横比）で
 *   見開きにするかを動的に決定する。横長（センターカラー等の見開き原稿）→ 1ページ、
 *   それ以外（縦長・正方形に近い）→ 見開き。
 * - 左右両ページの寸法が通知される前提で、片方でも横長を検出したら 1 ページ表示に
 *   切り替える（混在ページの表示崩れ対策）。
 */
export function useSpreadMode(): UseSpreadModeReturn {
    const [spreadMode, setSpreadMode] = useState<SpreadMode>('auto');
    // autoモード時にページサイズから計算した実効値（true=見開き、false=1ページ）
    const [autoIsSpread, setAutoIsSpread] = useState(true);

    const isSpread = spreadMode === 'auto' ? autoIsSpread : spreadMode === 'spread';

    const cycleSpreadMode = useCallback(() => {
        setSpreadMode((prev) =>
            prev === 'auto' ? 'spread' : prev === 'spread' ? 'single' : 'auto',
        );
    }, []);

    const handlePageSize = useCallback(
        (width: number, height: number) => {
            if (spreadMode !== 'auto') return;
            // 横長（見開き原稿）検出時のみ 1 ページ表示に確定。縦長検出時は何もしない
            // （= resetAutoSpread の初期値 true を維持）。これにより、現在表示中のペアの
            // 左右どちらか一方でも横長を検出すれば 1 ページ表示になる。
            // ペア切替時（pageNumber 変化）の再判定は呼び出し側で resetAutoSpread を呼ぶ。
            if (width > height * LANDSCAPE_RATIO_THRESHOLD) {
                setAutoIsSpread(false);
            }
        },
        [spreadMode],
    );

    const resetAutoSpread = useCallback(() => {
        setAutoIsSpread(true);
    }, []);

    return { spreadMode, isSpread, cycleSpreadMode, handlePageSize, resetAutoSpread };
}
