import { useCallback, useEffect, useState } from 'react';

import type { QaHistoryEntry, Scope } from '@/features/novel_db/types';
import { useNovelDbQuestion } from '@/hooks/novel_db';

import QuestionHistoryDetail from './QuestionHistoryDetail';
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
    const [selectedId, setSelectedId] = useState<number | null>(null);
    const [pendingAutoSelect, setPendingAutoSelect] = useState(false);

    const onCompleted = useCallback(() => {
        setPendingAutoSelect(true);
        void onHistoryRefetch();
    }, [onHistoryRefetch]);

    const { submit, stop, streamingText, isStreaming, error, isReplay } = useNovelDbQuestion(
        scope,
        onCompleted,
    );

    useEffect(() => {
        if (pendingAutoSelect && history.length > 0) {
            setSelectedId(history[0].id);
            setPendingAutoSelect(false);
        }
    }, [history, pendingAutoSelect]);

    const selectedEntry = history.find((h) => h.id === selectedId) ?? null;

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
                <div className="grid grid-cols-1 md:grid-cols-[260px_1fr] border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden bg-white dark:bg-gray-800">
                    <QuestionHistoryList
                        items={history}
                        isLoading={historyLoading}
                        selectedId={selectedId}
                        onSelect={setSelectedId}
                        onDelete={onHistoryDelete}
                    />
                    <QuestionHistoryDetail
                        selectedId={selectedId}
                        entry={selectedEntry}
                        onOpenImage={onOpenImage}
                    />
                </div>
            </div>
        </section>
    );
}
