import { useEffect, useRef, useCallback } from 'react';

interface UsePollingOptions {
    /** ポーリング間隔 (ms)。デフォルト: 2000 */
    interval?: number;
    /** false にするとポーリングを停止する。デフォルト: true */
    enabled?: boolean;
    /** true にすると初回マウント時に即時フェッチする。デフォルト: true */
    immediate?: boolean;
}

/**
 * 任意の非同期フェッチ関数を定期実行する共通ポーリングフック。
 *
 * - コンポーネントアンマウント時に自動でインターバルをクリア
 * - `enabled` を切り替えることでポーリングの開始/停止を制御できる
 * - fetcher の参照が変わっても古いクロージャを参照しないよう ref で管理
 */
export function usePolling(
    fetcher: () => Promise<void>,
    options: UsePollingOptions = {}
): { refetch: () => Promise<void> } {
    const { interval = 2000, enabled = true, immediate = true } = options;

    const intervalRef = useRef<number | null>(null);
    const fetcherRef = useRef(fetcher);

    // 最新の fetcher を ref に同期（古いクロージャ問題を防ぐ）
    useEffect(() => {
        fetcherRef.current = fetcher;
    }, [fetcher]);

    const refetch = useCallback(async () => {
        await fetcherRef.current();
    }, []);

    useEffect(() => {
        if (!enabled) {
            if (intervalRef.current !== null) {
                clearInterval(intervalRef.current);
                intervalRef.current = null;
            }
            return;
        }

        if (immediate) {
            fetcherRef.current();
        }

        intervalRef.current = window.setInterval(() => {
            fetcherRef.current();
        }, interval);

        return () => {
            if (intervalRef.current !== null) {
                clearInterval(intervalRef.current);
                intervalRef.current = null;
            }
        };
    }, [enabled, interval, immediate]);

    return { refetch };
}
