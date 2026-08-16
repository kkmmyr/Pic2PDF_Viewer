import { createParser } from 'eventsource-parser';

export async function postSseStream<T>(
    url: string,
    body: unknown,
    onEvent: (event: T) => 'stop' | void,
    signal?: AbortSignal,
): Promise<Error | null> {
    const response = await post(url, body, signal);
    if (response instanceof Error) return response;
    if (!response.ok) {
        const detail = await response.text().catch(() => '');
        return new Error(`HTTP ${response.status}: ${detail || response.statusText}`);
    }
    if (!response.body) return new Error('Response body is empty');
    return readEvents(response.body, onEvent, signal);
}

async function post(url: string, body: unknown, signal?: AbortSignal): Promise<Response | Error> {
    try {
        return await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
            body: JSON.stringify(body),
            signal,
        });
    } catch (error) {
        if (isAbortError(error)) return new Error('aborted', { cause: error });
        return error instanceof Error ? error : new Error(String(error));
    }
}

async function readEvents<T>(
    body: ReadableStream<Uint8Array>,
    onEvent: (event: T) => 'stop' | void,
    signal?: AbortSignal,
): Promise<Error | null> {
    const reader = body.getReader();
    const decoder = new TextDecoder();
    let shouldStop = false;
    let streamError: Error | null = null;
    const parser = createParser({
        maxBufferSize: 1024 * 1024,
        onEvent(message) {
            if (shouldStop) return;
            try {
                shouldStop = onEvent(JSON.parse(message.data) as T) === 'stop';
            } catch (error) {
                streamError = new Error('Invalid JSON in SSE event', { cause: error });
                shouldStop = true;
            }
        },
        onError(error) {
            streamError = error;
            shouldStop = true;
        },
    });
    try {
        while (!shouldStop) {
            if (signal?.aborted) return null;
            const { done, value } = await reader.read();
            if (done) break;
            parser.feed(decoder.decode(value, { stream: true }));
        }
        if (!shouldStop) {
            const tail = decoder.decode();
            if (tail) parser.feed(tail);
            parser.reset({ consume: true });
        }
    } catch (error) {
        if (isAbortError(error)) return null;
        return error instanceof Error ? error : new Error(String(error));
    } finally {
        if (shouldStop) void reader.cancel();
    }
    return streamError;
}

function isAbortError(error: unknown): boolean {
    return (
        typeof error === 'object' &&
        error !== null &&
        'name' in error &&
        error.name === 'AbortError'
    );
}
