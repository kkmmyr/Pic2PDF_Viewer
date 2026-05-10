/**
 * useNovelDbQuestion: SSE モック + 停止 + 連投警告。
 */
import { renderHook, act, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { useNovelDbQuestion } from '../hooks/novel_db/useNovelDbQuestion';
import type { Scope } from '../features/novel_db/types';

vi.mock('../features/novel_db/sse', () => ({
    streamQa: vi.fn(),
}));

import { streamQa } from '../features/novel_db/sse';

const SCOPE: Scope = { type: 'all' };

describe('useNovelDbQuestion', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it('submit で streamingText が累積される', async () => {
        vi.mocked(streamQa).mockImplementation(async (_body, handlers) => {
            handlers.onToken('hello');
            handlers.onToken(' world');
            handlers.onDone({ history_id: 1, eval_count: 10, done_reason: 'stop' });
        });

        const { result } = renderHook(() => useNovelDbQuestion(SCOPE));

        await act(async () => {
            await result.current.submit('質問?');
        });

        await waitFor(() => {
            expect(result.current.streamingText).toBe('hello world');
            expect(result.current.isStreaming).toBe(false);
        });
    });

    it('onError で error が設定される', async () => {
        vi.mocked(streamQa).mockImplementation(async (_body, handlers) => {
            handlers.onError(new Error('upstream failed'));
        });

        const { result } = renderHook(() => useNovelDbQuestion(SCOPE));
        await act(async () => {
            await result.current.submit('Q');
        });

        await waitFor(() => {
            expect(result.current.error).toBe('upstream failed');
            expect(result.current.isStreaming).toBe(false);
        });
    });

    it('onCompleted コールバックが呼ばれる', async () => {
        const onCompleted = vi.fn();
        vi.mocked(streamQa).mockImplementation(async (_body, handlers) => {
            handlers.onDone({ history_id: 1, eval_count: 5, done_reason: 'stop' });
        });

        const { result } = renderHook(() => useNovelDbQuestion(SCOPE, onCompleted));
        await act(async () => {
            await result.current.submit('Q');
        });

        await waitFor(() => {
            expect(onCompleted).toHaveBeenCalledTimes(1);
        });
    });

    it('isReplay は直前と完全一致の場合のみ true', async () => {
        vi.mocked(streamQa).mockImplementation(async (_body, handlers) => {
            handlers.onDone({ history_id: 1, eval_count: 1, done_reason: 'stop' });
        });

        const { result } = renderHook(() => useNovelDbQuestion(SCOPE));

        // 送信前は何でも false
        expect(result.current.isReplay('Q')).toBe(false);

        await act(async () => {
            await result.current.submit('Q1');
        });

        await waitFor(() => {
            expect(result.current.isReplay('Q1')).toBe(true);
            expect(result.current.isReplay('Q1 ')).toBe(true); // trim
            expect(result.current.isReplay('Q2')).toBe(false);
            expect(result.current.isReplay('')).toBe(false);
        });
    });

    it('stop で AbortController.abort が呼ばれる', async () => {
        let capturedSignal: AbortSignal | undefined;
        vi.mocked(streamQa).mockImplementation(async (_body, _handlers, signal) => {
            capturedSignal = signal;
            // 永続的に解決しないでおく
            return new Promise<void>(() => {});
        });

        const { result } = renderHook(() => useNovelDbQuestion(SCOPE));

        // submit を投げる（解決しない）
        act(() => {
            void result.current.submit('Q');
        });

        await waitFor(() => {
            expect(streamQa).toHaveBeenCalled();
            expect(capturedSignal).toBeDefined();
            expect(capturedSignal!.aborted).toBe(false);
        });

        act(() => {
            result.current.stop();
        });

        expect(capturedSignal!.aborted).toBe(true);
    });
});
