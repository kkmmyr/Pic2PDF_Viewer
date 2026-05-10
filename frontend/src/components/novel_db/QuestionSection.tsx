/**
 * 質問セクション。1 問 1 答 + 履歴展開。
 */
import { useCallback } from 'react';

import type { QaHistoryEntry, Scope } from '../../features/novel_db/types';
import { useNovelDbQuestion } from '../../hooks/novel_db';

import QuestionHistoryList from './QuestionHistoryList';
import QuestionInput from './QuestionInput';
import QuestionStreaming from './QuestionStreaming';

interface Props {
    scope: Scope;
    history: QaHistoryEntry[];
    historyLoading: boolean;
    onHistoryDelete: (id: number) => void;
    onHistoryRefetch: () => Promise<void> | void;
    onOpenImage: (book: string, pageNo: number) => void;
    disabled?: boolean;
}

export default function QuestionSection({
    scope,
    history,
    historyLoading,
    onHistoryDelete,
    onHistoryRefetch,
    onOpenImage,
    disabled,
}: Props) {
    const onCompleted = useCallback(() => {
        void onHistoryRefetch();
    }, [onHistoryRefetch]);

    const { submit, stop, streamingText, isStreaming, error, isReplay } = useNovelDbQuestion(
        scope,
        onCompleted,
    );

    return (
        <section className="space-y-3">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">質問</h2>
            <QuestionInput
                onSubmit={(q) => void submit(q)}
                disabled={disabled || isStreaming}
                isReplay={isReplay}
            />
            {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
            {isStreaming && <QuestionStreaming text={streamingText} onStop={stop} />}
            <div>
                <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
                    履歴
                </h3>
                <QuestionHistoryList
                    items={history}
                    isLoading={historyLoading}
                    onDelete={onHistoryDelete}
                    onOpenImage={onOpenImage}
                />
            </div>
        </section>
    );
}
