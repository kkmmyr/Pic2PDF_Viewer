import { afterEach, describe, expect, it, vi } from 'vitest';

import { streamQa } from '@/features/novel_db/sse';

function streamResponse(chunks: string[]): Response {
    const encoder = new TextEncoder();
    return new Response(
        new ReadableStream<Uint8Array>({
            start(controller) {
                chunks.forEach((chunk) => controller.enqueue(encoder.encode(chunk)));
                controller.close();
            },
        }),
        { status: 200, headers: { 'Content-Type': 'text/event-stream' } },
    );
}

describe('novel DB SSE parser', () => {
    afterEach(() => {
        vi.restoreAllMocks();
    });

    it('CRLF・複数data行・分割チャンクを1イベントとして処理する', async () => {
        vi.spyOn(globalThis, 'fetch').mockResolvedValue(
            streamResponse([
                'data: {"token":\r\n',
                'data: "hello"}\r\n\r\n',
                'data: {"done":true,"history_id":7}\r\n\r\n',
            ]),
        );
        const onToken = vi.fn();
        const onDone = vi.fn();
        const onError = vi.fn();

        await streamQa({ question: 'q', scope: { type: 'all' } }, { onToken, onDone, onError });

        expect(onToken).toHaveBeenCalledWith('hello');
        expect(onDone).toHaveBeenCalledWith({
            history_id: 7,
            eval_count: null,
            done_reason: null,
        });
        expect(onError).not.toHaveBeenCalled();
    });

    it('不正なJSONを黙って破棄せずエラーとして通知する', async () => {
        vi.spyOn(globalThis, 'fetch').mockResolvedValue(streamResponse(['data: {broken}\n\n']));
        const onError = vi.fn();

        await streamQa(
            { question: 'q', scope: { type: 'all' } },
            { onToken: vi.fn(), onDone: vi.fn(), onError },
        );

        expect(onError).toHaveBeenCalledWith(
            expect.objectContaining({ message: 'Invalid JSON in SSE event' }),
        );
    });
});
