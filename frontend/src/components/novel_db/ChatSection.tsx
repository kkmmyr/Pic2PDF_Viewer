/**
 * マルチターン会話 QA セクション（B-16）。
 *
 * ChatGPT 風 UI: 左にセッション一覧、右に現セッションのメッセージスレッド + 入力欄。
 * 新規セッションは画面controllerから渡された現在のscopeで開始。
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { MessageSquare } from 'lucide-react';

import { streamChatSession } from '@/features/novel_db/chat-sse';
import type { Scope } from '@/features/novel_db/types';
import { useChatSessionDetail, useChatSessions } from '@/hooks/novel_db';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import { ChatInput } from './ChatInput';
import { ChatMessageList } from './ChatMessageList';
import { SessionSidebar } from './SessionSidebar';

interface Props {
    scope: Scope;
    disabled?: boolean;
}

export default function ChatSection({ scope, disabled }: Props) {
    const {
        sessions,
        isLoading: sessionsLoading,
        refetch: refetchSessions,
        remove,
    } = useChatSessions(scope);
    const [activeId, setActiveId] = useState<number | null>(null);
    const { detail, streamingAnswer, setStreamingAnswer, reload, appendOptimisticUserMessage } =
        useChatSessionDetail(activeId);
    const [question, setQuestion] = useState('');
    const [sending, setSending] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [deleteTarget, setDeleteTarget] = useState<number | null>(null);
    const abortRef = useRef<AbortController | null>(null);

    useEffect(() => {
        return () => {
            abortRef.current?.abort();
        };
    }, []);

    const handleSend = useCallback(async () => {
        const q = question.trim();
        if (!q || sending || disabled) return;
        setError(null);
        setSending(true);
        setStreamingAnswer('');
        appendOptimisticUserMessage(q);

        const controller = new AbortController();
        abortRef.current = controller;

        const init =
            activeId === null ? { scope, question: q } : { sessionId: activeId, question: q };
        let accumulated = '';
        let nextSessionId: number | null = null;
        await streamChatSession(
            init,
            {
                onToken: (t) => {
                    accumulated += t;
                    setStreamingAnswer(accumulated);
                },
                onDone: async (ev) => {
                    nextSessionId = ev.session_id;
                },
                onError: (e) => {
                    setError(e.message);
                },
            },
            controller.signal,
        );

        // SSE 完了: 一覧 + 現セッションを再取得（楽観表示を実 DB 値に置き換え）
        if (nextSessionId !== null && nextSessionId !== activeId) {
            setActiveId(nextSessionId);
        }
        await refetchSessions();
        await reload();
        setStreamingAnswer('');
        setQuestion('');
        setSending(false);
        abortRef.current = null;
    }, [
        activeId,
        appendOptimisticUserMessage,
        disabled,
        question,
        refetchSessions,
        reload,
        scope,
        sending,
        setStreamingAnswer,
    ]);

    const handleAbort = useCallback(() => {
        abortRef.current?.abort();
        setSending(false);
        setStreamingAnswer('');
    }, [setStreamingAnswer]);

    const handleNew = () => {
        setActiveId(null);
        setStreamingAnswer('');
        setQuestion('');
        setError(null);
    };

    const handleDeleteConfirm = useCallback(async () => {
        if (deleteTarget === null) return;
        await remove(deleteTarget);
        if (activeId === deleteTarget) setActiveId(null);
        setDeleteTarget(null);
    }, [deleteTarget, remove, activeId]);

    return (
        <section className="space-y-3">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 flex items-center gap-2">
                <MessageSquare className="w-5 h-5" />
                会話 QA
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-[260px_1fr] gap-3 border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden bg-white dark:bg-gray-800">
                <SessionSidebar
                    sessions={sessions}
                    isLoading={sessionsLoading}
                    activeId={activeId}
                    onSelect={setActiveId}
                    onNew={handleNew}
                    onDelete={setDeleteTarget}
                />
                <div className="flex flex-col max-h-[600px]">
                    <ChatMessageList
                        detail={detail}
                        activeId={activeId}
                        streamingAnswer={streamingAnswer}
                        scope={scope}
                        sending={sending}
                    />
                    <ChatInput
                        question={question}
                        onQuestionChange={setQuestion}
                        onSend={handleSend}
                        onAbort={handleAbort}
                        sending={sending}
                        disabled={disabled}
                        error={error}
                        activeId={activeId}
                        scope={scope}
                    />
                </div>
            </div>
            <ConfirmDialog
                open={deleteTarget !== null}
                title="セッションの削除"
                message="このセッションを削除しますか？"
                confirmLabel="削除"
                danger
                onConfirm={handleDeleteConfirm}
                onCancel={() => setDeleteTarget(null)}
            />
        </section>
    );
}
