/**
 * novel_db /qa SSE クライアント。
 *
 * apiClient (axios) は SSE 非対応のため、本機能のみ fetch を直接利用する。
 * AbortController で停止可能。`onToken` / `onDone` / `onError` でイベント通知。
 */
import { API_CONFIG as API_URL_CONFIG } from '../../config/api';

import type { Scope } from './types';

export interface QaStreamRequest {
    question: string;
    scope: Scope;
}

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

interface SseEventPayload {
    token?: string;
    done?: boolean;
    history_id?: number;
    eval_count?: number | null;
    done_reason?: string | null;
    error?: string;
}

/**
 * /api/novel_db/qa を SSE で受信し、各イベントを handler に流す。
 * AbortSignal を渡すと停止可能（途中切断時はサーバ側で done_reason='canceled' で履歴保存）。
 *
 * @returns 完了 / 中断 / エラーを問わず Promise が解決する。
 */
export async function streamQa(
    body: QaStreamRequest,
    handlers: QaStreamHandlers,
    signal?: AbortSignal,
): Promise<void> {
    let response: Response;
    try {
        response = await fetch(`${API_URL_CONFIG.BASE_URL}/api/novel_db/qa`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                Accept: 'text/event-stream',
            },
            body: JSON.stringify(body),
            signal,
        });
    } catch (e) {
        if ((e as { name?: string }).name === 'AbortError') {
            return;
        }
        handlers.onError(e instanceof Error ? e : new Error(String(e)));
        return;
    }

    if (!response.ok) {
        const detail = await response.text().catch(() => '');
        handlers.onError(new Error(`HTTP ${response.status}: ${detail || response.statusText}`));
        return;
    }
    if (!response.body) {
        handlers.onError(new Error('Response body is empty'));
        return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    try {
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });

            // SSE の境界は空行 (\n\n)。境界ごとに切り出して `data: ...` を取り出す
            const segments = buffer.split('\n\n');
            buffer = segments.pop() ?? '';

            for (const segment of segments) {
                for (const line of segment.split('\n')) {
                    if (!line.startsWith('data: ')) continue;
                    let event: SseEventPayload;
                    try {
                        event = JSON.parse(line.slice(6)) as SseEventPayload;
                    } catch {
                        continue;
                    }
                    if (event.token !== undefined) {
                        handlers.onToken(event.token);
                    }
                    if (event.error !== undefined) {
                        handlers.onError(new Error(event.error));
                        return;
                    }
                    if (event.done) {
                        handlers.onDone({
                            history_id: event.history_id ?? -1,
                            eval_count: event.eval_count ?? null,
                            done_reason: event.done_reason ?? null,
                        });
                        return;
                    }
                }
            }
        }
    } catch (e) {
        if ((e as { name?: string }).name === 'AbortError') {
            return;
        }
        handlers.onError(e instanceof Error ? e : new Error(String(e)));
    }
}

// ---------------------------------------------------------------------------
// マルチターン会話 QA（B-16）
// ---------------------------------------------------------------------------

export interface ChatStreamInit {
    /** 続行ターン: 既存セッションに新メッセージ。 */
    sessionId?: number;
    /** 初手: scope を指定して新規セッションを作る。 */
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

/**
 * 会話セッションへの SSE。初手（scope 指定）/ 続行（sessionId 指定）の双方に対応。
 *
 * - 初手: POST /api/novel_db/qa/sessions （body: scope + question）
 * - 続行: POST /api/novel_db/qa/sessions/{id}/messages （body: question）
 */
export async function streamChatSession(
    init: ChatStreamInit,
    handlers: ChatStreamHandlers,
    signal?: AbortSignal,
): Promise<void> {
    const url =
        init.sessionId !== undefined
            ? `${API_URL_CONFIG.BASE_URL}/api/novel_db/qa/sessions/${init.sessionId}/messages`
            : `${API_URL_CONFIG.BASE_URL}/api/novel_db/qa/sessions`;
    const body =
        init.sessionId !== undefined
            ? { question: init.question }
            : { scope: init.scope, question: init.question };

    let response: Response;
    try {
        response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
            body: JSON.stringify(body),
            signal,
        });
    } catch (e) {
        if ((e as { name?: string }).name === 'AbortError') return;
        handlers.onError(e instanceof Error ? e : new Error(String(e)));
        return;
    }

    if (!response.ok) {
        const detail = await response.text().catch(() => '');
        handlers.onError(new Error(`HTTP ${response.status}: ${detail || response.statusText}`));
        return;
    }
    if (!response.body) {
        handlers.onError(new Error('Response body is empty'));
        return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    try {
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const segments = buffer.split('\n\n');
            buffer = segments.pop() ?? '';

            for (const segment of segments) {
                for (const line of segment.split('\n')) {
                    if (!line.startsWith('data: ')) continue;
                    let event: ChatSsePayload;
                    try {
                        event = JSON.parse(line.slice(6)) as ChatSsePayload;
                    } catch {
                        continue;
                    }
                    if (event.token !== undefined) {
                        handlers.onToken(event.token);
                    }
                    if (event.error !== undefined) {
                        handlers.onError(new Error(event.error));
                        return;
                    }
                    if (event.done) {
                        handlers.onDone({
                            session_id: event.session_id ?? -1,
                            message_id: event.message_id ?? -1,
                            eval_count: event.eval_count ?? null,
                            done_reason: event.done_reason ?? null,
                        });
                        return;
                    }
                }
            }
        }
    } catch (e) {
        if ((e as { name?: string }).name === 'AbortError') return;
        handlers.onError(e instanceof Error ? e : new Error(String(e)));
    }
}

// ---------------------------------------------------------------------------
// 読書会ディスカッション生成（B-20）
// ---------------------------------------------------------------------------

export interface DiscussionPersona {
    name: string;
    style_description: string;
}

export interface DiscussionGenerateRequest {
    book_name: string;
    personas: [DiscussionPersona, DiscussionPersona];
    num_turns: number;
}

export interface DiscussionTurnEvent {
    speaker: 'A' | 'B';
    text: string;
}

export interface DiscussionDoneEvent {
    saved_path?: string;
}

export interface DiscussionStreamHandlers {
    onTurn: (event: DiscussionTurnEvent) => void;
    onDone: (event: DiscussionDoneEvent) => void;
    onError: (error: Error) => void;
}

interface DiscussionSsePayload {
    type?: string;
    speaker?: string;
    text?: string;
    saved_path?: string;
    message?: string;
}

/** /api/novel/discussion/generate を SSE で受信する。 */
export async function streamDiscussion(
    body: DiscussionGenerateRequest,
    handlers: DiscussionStreamHandlers,
    signal?: AbortSignal,
): Promise<void> {
    let response: Response;
    try {
        response = await fetch(`${API_URL_CONFIG.BASE_URL}/api/novel/discussion/generate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
            body: JSON.stringify(body),
            signal,
        });
    } catch (e) {
        if ((e as { name?: string }).name === 'AbortError') return;
        handlers.onError(e instanceof Error ? e : new Error(String(e)));
        return;
    }

    if (!response.ok) {
        const detail = await response.text().catch(() => '');
        handlers.onError(new Error(`HTTP ${response.status}: ${detail || response.statusText}`));
        return;
    }
    if (!response.body) {
        handlers.onError(new Error('Response body is empty'));
        return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buf = '';

    try {
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buf += decoder.decode(value, { stream: true });
            const segments = buf.split('\n\n');
            buf = segments.pop() ?? '';

            for (const segment of segments) {
                for (const line of segment.split('\n')) {
                    if (!line.startsWith('data: ')) continue;
                    let event: DiscussionSsePayload;
                    try {
                        event = JSON.parse(line.slice(6)) as DiscussionSsePayload;
                    } catch {
                        continue;
                    }
                    if (event.type === 'turn' && event.speaker && event.text !== undefined) {
                        handlers.onTurn({
                            speaker: event.speaker as 'A' | 'B',
                            text: event.text,
                        });
                    } else if (event.type === 'done') {
                        handlers.onDone({ saved_path: event.saved_path });
                        return;
                    } else if (event.type === 'error' || event.message !== undefined) {
                        handlers.onError(new Error(event.message ?? 'Unknown error'));
                        return;
                    }
                }
            }
        }
    } catch (e) {
        if ((e as { name?: string }).name === 'AbortError') return;
        handlers.onError(e instanceof Error ? e : new Error(String(e)));
    }
}
