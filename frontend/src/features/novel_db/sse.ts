/**
 * novel_db / novel/discussion SSE クライアント。
 *
 * apiClient (axios) は SSE 非対応のため、本機能のみ fetch を直接利用する。
 * AbortController で停止可能。`onToken` / `onDone` / `onError` でイベント通知。
 */
import { API_CONFIG as API_URL_CONFIG } from '../../config/api';

import type { Scope } from './types';

// ---------------------------------------------------------------------------
// 共通 SSE フェッチヘルパー
// ---------------------------------------------------------------------------

/**
 * POST で SSE ストリームを受信し、JSON パース済みの各イベントを onEvent に流す。
 *
 * - AbortError は無視して null を返す（呼び出し側で中断扱い）。
 * - HTTP エラー / read 中の例外は Error を返す（throw しない）。
 * - onEvent が `'stop'` を返すとストリームを中断する。
 */
async function postSseStream<T>(
    url: string,
    body: unknown,
    onEvent: (event: T) => 'stop' | void,
    signal?: AbortSignal,
): Promise<Error | null> {
    let response: Response;
    try {
        response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
            body: JSON.stringify(body),
            signal,
        });
    } catch (e) {
        if ((e as { name?: string }).name === 'AbortError') return null;
        return e instanceof Error ? e : new Error(String(e));
    }

    if (!response.ok) {
        const detail = await response.text().catch(() => '');
        return new Error(`HTTP ${response.status}: ${detail || response.statusText}`);
    }
    if (!response.body) {
        return new Error('Response body is empty');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    try {
        outer: while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });

            // SSE の境界は空行 (\n\n)。境界ごとに切り出して `data: ...` を取り出す
            const segments = buffer.split('\n\n');
            buffer = segments.pop() ?? '';

            for (const segment of segments) {
                for (const line of segment.split('\n')) {
                    if (!line.startsWith('data: ')) continue;
                    let event: T;
                    try {
                        event = JSON.parse(line.slice(6)) as T;
                    } catch {
                        continue;
                    }
                    if (onEvent(event) === 'stop') break outer;
                }
            }
        }
    } catch (e) {
        if ((e as { name?: string }).name === 'AbortError') return null;
        return e instanceof Error ? e : new Error(String(e));
    }
    return null;
}

// ---------------------------------------------------------------------------
// QA（単発）
// ---------------------------------------------------------------------------

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
    const err = await postSseStream<SseEventPayload>(
        `${API_URL_CONFIG.BASE_URL}/api/novel_db/qa`,
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
    if (err) handlers.onError(err);
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
            ? `${API_URL_CONFIG.BASE_URL}/api/novel_db/sessions/${init.sessionId}/messages`
            : `${API_URL_CONFIG.BASE_URL}/api/novel_db/sessions`;
    const body =
        init.sessionId !== undefined
            ? { question: init.question }
            : { scope: init.scope, question: init.question };

    const err = await postSseStream<ChatSsePayload>(
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
    if (err) handlers.onError(err);
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
    const err = await postSseStream<DiscussionSsePayload>(
        `${API_URL_CONFIG.BASE_URL}/api/novel/discussion/generate`,
        body,
        (event) => {
            if (event.type === 'turn' && event.speaker && event.text !== undefined) {
                handlers.onTurn({ speaker: event.speaker as 'A' | 'B', text: event.text });
            } else if (event.type === 'done') {
                handlers.onDone({ saved_path: event.saved_path });
                return 'stop';
            } else if (event.type === 'error' || event.message !== undefined) {
                handlers.onError(new Error(event.message ?? 'Unknown error'));
                return 'stop';
            }
        },
        signal,
    );
    if (err) handlers.onError(err);
}
