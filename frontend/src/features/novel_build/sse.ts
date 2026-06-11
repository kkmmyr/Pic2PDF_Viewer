/**
 * novel_build SSE クライアント。
 * GET /api/novel/build/stream から Full Build キュー状態を受信する。
 * EventSource（ネイティブ）を使用。停止は返却した close 関数で行う。
 */
import { API_CONFIG } from '@/config/api';

import type { BuildQueueStatus, BuildStreamHandlers } from './types';

export type { BuildJob, FinishedJob, BuildQueueStatus, BuildStreamHandlers } from './types';

/**
 * SSE ストリームに接続し、キュー状態を受信する。
 * @returns close 関数（呼び出しで接続を切断する）
 */
export function connectBuildStream(handlers: BuildStreamHandlers): () => void {
    const url = `${API_CONFIG.BASE_URL}/api/novel/build/stream`;
    const es = new EventSource(url);

    es.onmessage = (event) => {
        try {
            const status = JSON.parse(event.data) as BuildQueueStatus;
            handlers.onStatus(status);
        } catch {
            // パース失敗は無視
        }
    };

    es.onerror = (event) => {
        handlers.onError(event);
    };

    return () => es.close();
}
