import { useEffect, useRef } from 'react';

import type { Scope } from '@/features/novel_db/types';
import type { useChatSessionDetail } from '@/hooks/novel_db';

interface ChatMessageListProps {
    detail: ReturnType<typeof useChatSessionDetail>['detail'];
    activeId: number | null;
    streamingAnswer: string;
    scope: Scope;
    sending: boolean;
}

export function ChatMessageList({
    detail,
    activeId,
    streamingAnswer,
    scope,
    sending,
}: ChatMessageListProps) {
    const scrollRef = useRef<HTMLDivElement | null>(null);

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
                        senderRole={m.role}
                        content={m.content}
                    />
                ))
            )}
            {sending && streamingAnswer && (
                <MessageBubble senderRole="assistant" content={streamingAnswer} streaming />
            )}
        </div>
    );
}

// ---------------------------------------------------------------------------

interface MessageBubbleProps {
    senderRole: 'user' | 'assistant' | 'system';
    content: string;
    streaming?: boolean;
}

function MessageBubble({ senderRole, content, streaming }: MessageBubbleProps) {
    if (senderRole === 'system') return null;
    const isUser = senderRole === 'user';
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
