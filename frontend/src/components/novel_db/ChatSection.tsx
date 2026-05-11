/**
 * マルチターン会話 QA セクション（B-16）。
 *
 * ChatGPT 風 UI: 左にセッション一覧、右に現セッションのメッセージスレッド + 入力欄。
 * 新規セッションは現在の scope（NovelDbHeader のスコープセレクタ）で開始。
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { MessageSquare, Plus, Trash2 } from 'lucide-react';

import { streamChatSession } from '../../features/novel_db/sse';
import type { Scope } from '../../features/novel_db/types';
import { useChatSessionDetail, useChatSessions } from '../../hooks/novel_db';

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
    } = useChatSessions();
    const [activeId, setActiveId] = useState<number | null>(null);
    const { detail, streamingAnswer, setStreamingAnswer, reload, appendOptimisticUserMessage } =
        useChatSessionDetail(activeId);
    const [question, setQuestion] = useState('');
    const [sending, setSending] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const abortRef = useRef<AbortController | null>(null);

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

    const handleDelete = useCallback(
        async (id: number) => {
            if (!window.confirm('このセッションを削除しますか？')) return;
            await remove(id);
            if (activeId === id) setActiveId(null);
        },
        [activeId, remove],
    );

    return (
        <section className="space-y-3">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 flex items-center gap-2">
                <MessageSquare className="w-5 h-5" />
                会話 QA
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-[260px_1fr] gap-3 border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden bg-white dark:bg-gray-800">
                <SessionListPane
                    sessions={sessions}
                    isLoading={sessionsLoading}
                    activeId={activeId}
                    onSelect={setActiveId}
                    onNew={handleNew}
                    onDelete={handleDelete}
                />
                <ChatThreadPane
                    detail={detail}
                    activeId={activeId}
                    streamingAnswer={streamingAnswer}
                    scope={scope}
                    question={question}
                    onQuestionChange={setQuestion}
                    onSend={handleSend}
                    onAbort={handleAbort}
                    sending={sending}
                    disabled={disabled}
                    error={error}
                />
            </div>
        </section>
    );
}

// ---------------------------------------------------------------------------
// Session List Pane
// ---------------------------------------------------------------------------

interface SessionListPaneProps {
    sessions: ReturnType<typeof useChatSessions>['sessions'];
    isLoading: boolean;
    activeId: number | null;
    onSelect: (id: number | null) => void;
    onNew: () => void;
    onDelete: (id: number) => void;
}

function SessionListPane({
    sessions,
    isLoading,
    activeId,
    onSelect,
    onNew,
    onDelete,
}: SessionListPaneProps) {
    return (
        <div className="border-r border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/30 max-h-[600px] overflow-y-auto">
            <button
                type="button"
                onClick={onNew}
                className="w-full flex items-center gap-1.5 px-3 py-2 text-sm font-medium border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 hover:bg-primary-50 dark:hover:bg-primary-900/30 text-gray-800 dark:text-gray-100"
            >
                <Plus className="w-4 h-4" />
                新しい会話
            </button>
            {isLoading ? (
                <p className="p-3 text-xs text-gray-500">読み込み中...</p>
            ) : sessions.length === 0 ? (
                <p className="p-3 text-xs text-gray-500">セッションなし</p>
            ) : (
                <ul>
                    {sessions.map((s) => {
                        const isActive = s.id === activeId;
                        const scopeLabel =
                            s.scope_type === 'book'
                                ? `本: ${s.scope_id ?? ''}`
                                : s.scope_type === 'series'
                                  ? `シリーズ: ${s.scope_id ?? ''}`
                                  : '全件';
                        return (
                            <li
                                key={s.id}
                                className={`group border-b border-gray-200 dark:border-gray-700 ${isActive ? 'bg-primary-50 dark:bg-primary-900/30' : ''}`}
                            >
                                <button
                                    type="button"
                                    onClick={() => onSelect(s.id)}
                                    className="w-full text-left px-3 py-2 hover:bg-gray-100 dark:hover:bg-gray-800"
                                >
                                    <div
                                        className="text-xs font-medium text-gray-900 dark:text-gray-100 truncate"
                                        title={s.title ?? `セッション ${s.id}`}
                                    >
                                        {s.title ?? `セッション ${s.id}`}
                                    </div>
                                    <div
                                        className="text-[10px] text-gray-500 dark:text-gray-400 truncate"
                                        title={scopeLabel}
                                    >
                                        {scopeLabel} · {s.message_count} 件
                                    </div>
                                </button>
                                <button
                                    type="button"
                                    onClick={() => onDelete(s.id)}
                                    title="削除"
                                    className="opacity-0 group-hover:opacity-100 absolute right-1 top-1 p-1 text-gray-500 hover:text-red-600"
                                >
                                    <Trash2 className="w-3.5 h-3.5" />
                                </button>
                            </li>
                        );
                    })}
                </ul>
            )}
        </div>
    );
}

// ---------------------------------------------------------------------------
// Chat Thread Pane
// ---------------------------------------------------------------------------

interface ChatThreadPaneProps {
    detail: ReturnType<typeof useChatSessionDetail>['detail'];
    activeId: number | null;
    streamingAnswer: string;
    scope: Scope;
    question: string;
    onQuestionChange: (s: string) => void;
    onSend: () => void;
    onAbort: () => void;
    sending: boolean;
    disabled?: boolean;
    error: string | null;
}

function ChatThreadPane({
    detail,
    activeId,
    streamingAnswer,
    scope,
    question,
    onQuestionChange,
    onSend,
    onAbort,
    sending,
    disabled,
    error,
}: ChatThreadPaneProps) {
    const scrollRef = useRef<HTMLDivElement | null>(null);

    // メッセージ追加 / streaming token のたびに最下部へスクロール
    useEffect(() => {
        const el = scrollRef.current;
        if (el) el.scrollTop = el.scrollHeight;
    }, [detail?.messages.length, streamingAnswer]);

    const messages = detail?.messages ?? [];
    const placeholderScope =
        scope.type === 'book'
            ? `本: ${scope.id ?? ''}`
            : scope.type === 'series'
              ? `シリーズ: ${scope.id ?? ''}`
              : '全件';

    return (
        <div className="flex flex-col max-h-[600px]">
            <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-3">
                {activeId === null ? (
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                        新しい会話を始めます（スコープ: {placeholderScope}
                        ）。質問を入力してください。
                    </p>
                ) : messages.length === 0 ? (
                    <p className="text-sm text-gray-500 dark:text-gray-400">読み込み中...</p>
                ) : (
                    messages.map((m) => (
                        <MessageBubble
                            key={m.id !== -1 ? m.id : `optimistic-${m.created_at}`}
                            role={m.role}
                            content={m.content}
                        />
                    ))
                )}
                {sending && streamingAnswer && (
                    <MessageBubble role="assistant" content={streamingAnswer} streaming />
                )}
            </div>
            {error && (
                <p className="px-4 py-1.5 text-xs text-red-600 dark:text-red-400 border-t border-red-200 dark:border-red-800">
                    {error}
                </p>
            )}
            <div className="border-t border-gray-200 dark:border-gray-700 p-2 flex gap-2">
                <textarea
                    value={question}
                    onChange={(e) => onQuestionChange(e.target.value)}
                    onKeyDown={(e) => {
                        // Ctrl+Enter / Cmd+Enter で送信
                        if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                            e.preventDefault();
                            onSend();
                        }
                    }}
                    rows={2}
                    placeholder={`質問を入力（Ctrl+Enter で送信）${activeId === null ? `スコープ: ${placeholderScope}` : ''}`}
                    disabled={sending || disabled}
                    className="flex-1 text-sm px-2 py-1.5 rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 disabled:opacity-50 resize-none"
                />
                {sending ? (
                    <button
                        type="button"
                        onClick={onAbort}
                        className="px-3 py-1 text-xs rounded bg-red-100 dark:bg-red-900/40 hover:bg-red-200 text-red-700 dark:text-red-200"
                    >
                        停止
                    </button>
                ) : (
                    <button
                        type="button"
                        onClick={onSend}
                        disabled={!question.trim() || disabled}
                        className="px-3 py-1 text-xs rounded bg-primary-600 hover:bg-primary-700 text-white disabled:opacity-50"
                    >
                        送信
                    </button>
                )}
            </div>
        </div>
    );
}

// ---------------------------------------------------------------------------
// Message Bubble
// ---------------------------------------------------------------------------

interface MessageBubbleProps {
    role: 'user' | 'assistant' | 'system';
    content: string;
    streaming?: boolean;
}

function MessageBubble({ role, content, streaming }: MessageBubbleProps) {
    if (role === 'system') return null; // system は UI 非表示
    const isUser = role === 'user';
    return (
        <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
            <div
                className={`max-w-[85%] text-sm whitespace-pre-wrap px-3 py-2 rounded-lg ${
                    isUser
                        ? 'bg-primary-600 text-white'
                        : 'bg-gray-100 dark:bg-gray-700 text-gray-900 dark:text-gray-100'
                }`}
            >
                {content}
                {streaming && <span className="ml-1 animate-pulse">▌</span>}
            </div>
        </div>
    );
}
