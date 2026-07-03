import { useEffect, useState } from 'react';

import { fetchQaHistoryDetail } from '@/features/novel_db/api';
import type { QaHistoryDetail, QaHistoryEntry } from '@/features/novel_db/types';
import { scopeLabel } from '@/features/novel_db/scopeLabel';
import { formatElapsedSeconds, formatSqliteUtcAsJst } from '@/utils/date';

interface Props {
    selectedId: number | null;
    entry: QaHistoryEntry | null;
    onOpenImage: (book: string, pageNo: number) => void;
}

export default function QuestionHistoryDetail({ selectedId, entry, onOpenImage }: Props) {
    const [detail, setDetail] = useState<QaHistoryDetail | null>(null);
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (selectedId === null) {
            setDetail(null);
            return;
        }
        let canceled = false;
        setLoading(true);
        void fetchQaHistoryDetail(selectedId)
            .then((d) => {
                if (!canceled) {
                    setDetail(d);
                    setLoading(false);
                }
            })
            .catch(() => {
                if (!canceled) setLoading(false);
            });
        return () => {
            canceled = true;
        };
    }, [selectedId]);

    if (selectedId === null || !entry) {
        return (
            <div className="flex items-center justify-center p-8 text-sm text-gray-500 dark:text-gray-400">
                履歴を選択すると詳細を表示します
            </div>
        );
    }

    const elapsed = formatElapsedSeconds(entry.asked_at, entry.finished_at);

    return (
        <div className="flex flex-col max-h-[600px] overflow-y-auto p-4 space-y-3">
            <div>
                <div className="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-1">
                    質問
                </div>
                <div className="text-sm text-gray-900 dark:text-gray-100 whitespace-pre-wrap">
                    {entry.question}
                </div>
                <div className="flex flex-wrap gap-2 mt-1 text-xs text-gray-500 dark:text-gray-400">
                    <span>{formatSqliteUtcAsJst(entry.asked_at)}</span>
                    {elapsed && (
                        <>
                            <span>·</span>
                            <span>応答 {elapsed}</span>
                        </>
                    )}
                    <span>·</span>
                    <span>{scopeLabel(entry.scope)}</span>
                </div>
            </div>

            {loading ? (
                <p className="text-xs text-gray-500">読み込み中…</p>
            ) : detail ? (
                <>
                    <div>
                        <div className="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-1">
                            回答
                        </div>
                        <div className="text-sm text-gray-800 dark:text-gray-200 whitespace-pre-wrap leading-relaxed">
                            {detail.answer || <span className="text-gray-400">（応答なし）</span>}
                        </div>
                    </div>
                    {detail.context.length > 0 && (
                        <div>
                            <div className="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-1">
                                参照したページ
                            </div>
                            <ul className="flex flex-wrap gap-1.5">
                                {detail.context.map((c, idx) => (
                                    <li key={`${c.book_name}-${c.page_no}-${idx}`}>
                                        <button
                                            onClick={() => onOpenImage(c.book_name, c.page_no)}
                                            className="text-xs px-2 py-0.5 rounded border border-gray-300 dark:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-200"
                                        >
                                            {c.book_name} p{c.page_no}
                                        </button>
                                    </li>
                                ))}
                            </ul>
                        </div>
                    )}
                </>
            ) : null}
        </div>
    );
}
