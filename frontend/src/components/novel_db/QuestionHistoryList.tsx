/**
 * 質問履歴一覧（時系列降順、展開可能）。
 */
import type { QaHistoryEntry } from '../../features/novel_db/types';

import QuestionHistoryItem from './QuestionHistoryItem';

interface Props {
    items: QaHistoryEntry[];
    isLoading: boolean;
    onDelete: (id: number) => void;
    onOpenImage: (book: string, pageNo: number) => void;
}

export default function QuestionHistoryList({ items, isLoading, onDelete, onOpenImage }: Props) {
    if (isLoading && items.length === 0) {
        return <p className="text-sm text-gray-500">履歴を読み込み中…</p>;
    }
    if (items.length === 0) {
        return <p className="text-sm text-gray-500">まだ履歴がありません。</p>;
    }
    return (
        <ul className="space-y-2">
            {items.map((entry) => (
                <QuestionHistoryItem
                    key={entry.id}
                    entry={entry}
                    onDelete={onDelete}
                    onOpenImage={onOpenImage}
                />
            ))}
        </ul>
    );
}
