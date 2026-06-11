/**
 * 会話セッション一覧 + 詳細 + SSE ストリーム（B-16）。
 *
 * - 一覧: useChatSessions（API: GET /qa/sessions）
 * - 詳細: useChatSessionDetail（API: GET /qa/sessions/{id}）
 * - 送信: streamChatSession（SSE）
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

import {
    deleteChatSession,
    fetchChatSessionDetail,
    fetchChatSessions,
} from '@/features/novel_db/api';
import type {
    ChatMessage,
    ChatSessionDetail,
    ChatSessionSummary,
    Scope,
} from '@/features/novel_db/types';

export interface UseChatSessions {
    sessions: ChatSessionSummary[];
    isLoading: boolean;
    error: string | null;
    refetch: () => Promise<void>;
    remove: (id: number) => Promise<void>;
}

export function useChatSessions(scope?: Scope): UseChatSessions {
    const queryClient = useQueryClient();
    const scopeType = scope?.type;
    const scopeId = scope?.id ?? null;
    const queryKey = ['chatSessions', scopeType, scopeId] as const;

    const query = useQuery({
        queryKey,
        queryFn: () =>
            fetchChatSessions(0, 50, scopeType ? { type: scopeType, id: scopeId } : undefined),
        staleTime: Infinity,
    });

    const removeMutation = useMutation({
        mutationFn: (id: number) => deleteChatSession(id),
        onSuccess: () =>
            queryClient.invalidateQueries({ queryKey: ['chatSessions'], refetchType: 'active' }),
    });

    return {
        sessions: Array.isArray(query.data) ? query.data : [],
        isLoading: query.isLoading,
        error: query.error instanceof Error ? query.error.message : null,
        refetch: async () => {
            await queryClient.refetchQueries({ queryKey });
        },
        remove: (id: number) => removeMutation.mutateAsync(id),
    };
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
    const queryClient = useQueryClient();
    const queryKey = useMemo(() => ['chatSessionDetail', sessionId] as const, [sessionId]);

    const query = useQuery({
        queryKey,
        queryFn: () => fetchChatSessionDetail(sessionId!),
        enabled: sessionId !== null,
        staleTime: 0,
    });

    const [streamingAnswer, setStreamingAnswer] = useState('');

    // sessionId 変更時に streamingAnswer をリセット
    useEffect(() => {
        setStreamingAnswer('');
    }, [sessionId]);

    const appendOptimisticUserMessage = useCallback(
        (content: string) => {
            queryClient.setQueryData(queryKey, (old: ChatSessionDetail | undefined) => {
                if (!old) return old;
                const optimistic: ChatMessage = {
                    id: -1,
                    role: 'user',
                    content,
                    eval_count: null,
                    done_reason: null,
                    created_at: new Date().toISOString(),
                };
                return { ...old, messages: [...old.messages, optimistic] };
            });
        },
        [queryClient, queryKey],
    );

    const reload = useCallback(async () => {
        if (sessionId === null) return;
        await queryClient.invalidateQueries({ queryKey });
    }, [queryClient, queryKey, sessionId]);

    return {
        detail: query.data ?? null,
        isLoading: query.isLoading,
        error: query.error instanceof Error ? query.error.message : null,
        streamingAnswer,
        setStreamingAnswer,
        reload,
        appendOptimisticUserMessage,
    };
}
