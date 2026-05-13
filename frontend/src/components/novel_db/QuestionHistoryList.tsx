import type { QaHistoryEntry } from '../../features/novel_db/types';

import QuestionHistoryItem from './QuestionHistoryItem';

interface Props {
    items: QaHistoryEntry[];
    isLoading: boolean;
    selectedId: number | null;
    onSelect: (id: number) => void;
    onDelete: (id: number) => void;
}

export default function QuestionHistoryList({
    items,
    isLoading,
    selectedId,
    onSelect,
    onDelete,
}: Props) {
    const inner =
        isLoading && items.length === 0 ? (
            <p className="p-3 text-xs text-gray-500">読み込み中…</p>
        ) : items.length === 0 ? (
            <p className="p-3 text-xs text-gray-500">まだ履歴がありません。</p>
        ) : (
            <ul>
                {items.map((entry) => (
                    <QuestionHistoryItem
                        key={entry.id}
                        entry={entry}
                        isActive={entry.id === selectedId}
                        onSelect={onSelect}
                        onDelete={onDelete}
                    />
                ))}
            </ul>
        );

    return (
        <div className="border-r border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/30 max-h-[600px] overflow-y-auto">
            {inner}
        </div>
    );
}
