import { API_CONFIG } from '@/config/api';
import { postSseStream } from '@/features/novel_db/sse-transport';
import type { Scope } from '@/features/novel_db/types';

export interface ChatStreamInit {
    sessionId?: number;
    scope?: Scope;
    question: string;
}

export interface ChatDoneEvent {
    session_id: number;
    message_id: number;
    eval_count: number | null;
    done_reason: string | null;
}

export interface ChatStreamHandlers {
    onToken: (text: string) => void;
    onDone: (event: ChatDoneEvent) => void;
    onError: (error: Error) => void;
}

interface ChatSsePayload {
    token?: string;
    done?: boolean;
    session_id?: number;
    message_id?: number;
    eval_count?: number | null;
    done_reason?: string | null;
    error?: string;
}

export async function streamChatSession(
    init: ChatStreamInit,
    handlers: ChatStreamHandlers,
    signal?: AbortSignal,
): Promise<void> {
    const continuing = init.sessionId !== undefined;
    const url = continuing
        ? `${API_CONFIG.BASE_URL}/api/novel_db/sessions/${init.sessionId}/messages`
        : `${API_CONFIG.BASE_URL}/api/novel_db/sessions`;
    const body = continuing
        ? { question: init.question }
        : { scope: init.scope, question: init.question };
    const error = await postSseStream<ChatSsePayload>(
        url,
        body,
        (event) => {
            if (event.token !== undefined) handlers.onToken(event.token);
            if (event.error !== undefined) {
                handlers.onError(new Error(event.error));
                return 'stop';
            }
            if (event.done) {
                handlers.onDone({
                    session_id: event.session_id ?? -1,
                    message_id: event.message_id ?? -1,
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
