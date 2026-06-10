import { useRef, useEffect } from 'react';

import type { ReadState } from '../../types';

interface UseReadProgressTrackerProps {
    selectedPdf: string;
    currentPath: string;
    isAtLastSpread: boolean;
    getReadState: (path: string, name: string) => string | undefined;
    setReadState: (path: string, names: string[], state: ReadState | '') => Promise<void>;
}

/**
 * 最終ページ到達時に read_state='done' を 1 度だけ記録する。
 *
 * - selectedPdf 切替時にガードをリセットして次の書籍に備える
 * - PATCH 失敗時はガードを外して次回再試行を許可する
 */
export function useReadProgressTracker({
    selectedPdf,
    currentPath,
    isAtLastSpread,
    getReadState,
    setReadState,
}: UseReadProgressTrackerProps): void {
    const doneSentForRef = useRef<string | null>(null);

    useEffect(() => {
        if (!isAtLastSpread) return;
        if (doneSentForRef.current === selectedPdf) return;
        if (getReadState(currentPath, selectedPdf) === 'done') {
            doneSentForRef.current = selectedPdf;
            return;
        }
        doneSentForRef.current = selectedPdf;
        setReadState(currentPath, [selectedPdf], 'done').catch(() => {
            doneSentForRef.current = null;
        });
    }, [isAtLastSpread, selectedPdf, currentPath, getReadState, setReadState]);

    useEffect(() => {
        doneSentForRef.current = null;
    }, [selectedPdf]);
}
