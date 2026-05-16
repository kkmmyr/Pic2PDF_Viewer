/**
 * 会話セッション一覧 + 詳細 + SSE ストリーム（B-16）。
 *
 * - 一覧: useChatSessions（API: GET /qa/sessions）
 * - 詳細: useChatSessionDetail（API: GET /qa/sessions/{id}）
 * - 送信: streamChatSession（SSE）
 */
import { useCallback, useEffect, useState } from 'react';

import {
    deleteChatSession,
    fetchChatSessionDetail,
    fetchChatSessions,
} from '../../features/novel_db/api';
import type {
    ChatMessage,
    ChatSessionDetail,
    ChatSessionSummary,
    Scope,
} from '../../features/novel_db/types';

export interface UseChatSessions {
    sessions: ChatSessionSummary[];
    isLoading: boolean;
    error: string | null;
    refetch: () => Promise<void>;
    remove: (id: number) => Promise<void>;
}

export function useChatSessions(scope?: Scope): UseChatSessions {
    const [sessions, setSessions] = useState<ChatSessionSummary[]>([]);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const scopeType = scope?.type;
    const scopeId = scope?.id ?? null;

    const refetch = useCallback(async () => {
        setIsLoading(true);
        setError(null);
        try {
            const filterScope = scopeType ? { type: scopeType, id: scopeId } : undefined;
            const list = await fetchChatSessions(0, 50, filterScope);
            setSessions(Array.isArray(list) ? list : []);
        } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
        } finally {
            setIsLoading(false);
        }
    }, [scopeType, scopeId]);

    const remove = useCallback(
        async (id: number) => {
            await deleteChatSession(id);
            await refetch();
        },
        [refetch],
    );

    useEffect(() => {
        void refetch();
    }, [refetch]);

    return { sessions, isLoading, error, refetch, remove };
}

export interface UseChatSessionDetail {
    detail: ChatSessionDetail | null;
    isLoading: boolean;
    error: string | null;
    /** SSE 中の暫定 assistant tokens を表示するためのバッファ。完了時に reset。 */
    streamingAnswer: string;
    setStreamingAnswer: (s: string) => void;
    /** SSE 完了後にサーバから最新詳細を再取得する。 */
    reload: () => Promise<void>;
    /** ローカルに新 user メッセージを楽観的に追加（送信直後の表示用）。 */
    appendOptimisticUserMessage: (content: string) => void;
}

export function useChatSessionDetail(sessionId: number | null): UseChatSessionDetail {
    const [detail, setDetail] = useState<ChatSessionDetail | null>(null);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [streamingAnswer, setStreamingAnswer] = useState('');

    const reload = useCallback(async () => {
        if (sessionId === null) {
            setDetail(null);
            return;
        }
        setIsLoading(true);
        setError(null);
        try {
            const d = await fetchChatSessionDetail(sessionId);
            setDetail(d);
        } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
            setDetail(null);
        } finally {
            setIsLoading(false);
        }
    }, [sessionId]);

    const appendOptimisticUserMessage = useCallback((content: string) => {
        setDetail((cur) => {
            if (!cur) return cur;
            const optimistic: ChatMessage = {
                id: -1,
                role: 'user',
                content,
                eval_count: null,
                done_reason: null,
                created_at: new Date().toISOString(),
            };
            return { ...cur, messages: [...cur.messages, optimistic] };
        });
    }, []);

    useEffect(() => {
        setStreamingAnswer('');
        void reload();
    }, [reload]);

    return {
        detail,
        isLoading,
        error,
        streamingAnswer,
        setStreamingAnswer,
        reload,
        appendOptimisticUserMessage,
    };
}
