import type { Scope } from '@/features/novel_db/types';

interface ChatInputProps {
    question: string;
    onQuestionChange: (s: string) => void;
    onSend: () => void;
    onAbort: () => void;
    sending: boolean;
    disabled?: boolean;
    error: string | null;
    activeId: number | null;
    scope: Scope;
}

export function ChatInput({
    question,
    onQuestionChange,
    onSend,
    onAbort,
    sending,
    disabled,
    error,
    activeId,
    scope,
}: ChatInputProps) {
    const placeholderScope =
        scope.type === 'book'
            ? `本: ${scope.id ?? ''}`
            : scope.type === 'series'
              ? `シリーズ: ${scope.id ?? ''}`
              : '全件';

    return (
        <>
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
        </>
    );
}
