/**
 * Gemma SSE 質問応答フック。
 *
 * - `submit(question)`: 送信開始、トークンが届くたび `streamingText` を更新
 * - `stop()`: AbortController で送信中断（サーバ側で done_reason='canceled' で履歴保存）
 * - `isReplay(q)`: セッション内の直前質問と完全一致なら true（連投警告用）
 *
 * セッション内のみで `lastQuestion` を保持。リロードで自動リセット。
 */
import { useCallback, useRef, useState } from 'react';

import { streamQa } from '@/features/novel_db/sse';
import type { Scope } from '@/features/novel_db/types';

export interface UseNovelDbQuestion {
    submit: (question: string) => Promise<void>;
    stop: () => void;
    streamingText: string;
    isStreaming: boolean;
    error: string | null;
    isReplay: (q: string) => boolean;
}

export function useNovelDbQuestion(scope: Scope, onCompleted?: () => void): UseNovelDbQuestion {
    const [streamingText, setStreamingText] = useState('');
    const [isStreaming, setIsStreaming] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [lastQuestion, setLastQuestion] = useState('');
    const abortRef = useRef<AbortController | null>(null);

    const submit = useCallback(
        async (question: string) => {
            if (isStreaming) return;
            const controller = new AbortController();
            abortRef.current = controller;
            setLastQuestion(question);
            setStreamingText('');
            setError(null);
            setIsStreaming(true);
            try {
                await streamQa(
                    { question, scope },
                    {
                        onToken: (text) => setStreamingText((prev) => prev + text),
                        onDone: () => {
                            setIsStreaming(false);
                            onCompleted?.();
                        },
                        onError: (e) => {
                            setError(e.message);
                            setIsStreaming(false);
                        },
                    },
                    controller.signal,
                );
            } finally {
                // streamQa が return する場合（abort / done / error）はすべて isStreaming を解除
                setIsStreaming(false);
            }
        },
        [scope, isStreaming, onCompleted],
    );

    const stop = useCallback(() => {
        abortRef.current?.abort();
        setIsStreaming(false);
        onCompleted?.();
    }, [onCompleted]);

    const isReplay = useCallback(
        (q: string) => {
            const t = q.trim();
            return t.length > 0 && t === lastQuestion.trim();
        },
        [lastQuestion],
    );

    return { submit, stop, streamingText, isStreaming, error, isReplay };
}
