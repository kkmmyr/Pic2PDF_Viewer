import { API_CONFIG } from '@/config/api';
import { postSseStream } from '@/features/novel_db/sse-transport';
import type { components } from '@/types/api';

export type QaStreamRequest = components['schemas']['QaRequest'];

export interface QaDoneEvent {
    history_id: number;
    eval_count: number | null;
    done_reason: string | null;
}

export interface QaStreamHandlers {
    onToken: (text: string) => void;
    onDone: (event: QaDoneEvent) => void;
    onError: (error: Error) => void;
}

interface QaSsePayload {
    token?: string;
    done?: boolean;
    history_id?: number;
    eval_count?: number | null;
    done_reason?: string | null;
    error?: string;
}

export async function streamQa(
    body: QaStreamRequest,
    handlers: QaStreamHandlers,
    signal?: AbortSignal,
): Promise<void> {
    const error = await postSseStream<QaSsePayload>(
        `${API_CONFIG.BASE_URL}/api/novel_db/qa`,
        body,
        (event) => {
            if (event.token !== undefined) handlers.onToken(event.token);
            if (event.error !== undefined) {
                handlers.onError(new Error(event.error));
                return 'stop';
            }
            if (event.done) {
                handlers.onDone({
                    history_id: event.history_id ?? -1,
                    eval_count: event.eval_count ?? null,
                    done_reason: event.done_reason ?? null,
                });
                return 'stop';
            }
        },
        signal,
    );
    if (error && error.message !== 'aborted') handlers.onError(error);
}
