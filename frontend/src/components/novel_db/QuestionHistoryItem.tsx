/**
 * 履歴 1 件分（折りたたみ展開、引用ページクリックで画像モーダル）。
 */
import { useEffect, useState } from 'react';
import { ChevronDown, ChevronRight, Trash2 } from 'lucide-react';

import { fetchQaHistoryDetail } from '../../features/novel_db/api';
import type { QaHistoryDetail, QaHistoryEntry } from '../../features/novel_db/types';
import { ConfirmDialog } from '../ui/ConfirmDialog';

interface Props {
    entry: QaHistoryEntry;
    onDelete: (id: number) => void;
    onOpenImage: (book: string, pageNo: number) => void;
}

function scopeLabel(entry: QaHistoryEntry): string {
    if (entry.scope.type === 'all') return '全件';
    if (entry.scope.type === 'series') return `シリーズ: ${entry.scope.id ?? ''}`;
    return `単冊: ${entry.scope.id ?? ''}`;
}

export default function QuestionHistoryItem({ entry, onDelete, onOpenImage }: Props) {
    const [expanded, setExpanded] = useState(false);
    const [detail, setDetail] = useState<QaHistoryDetail | null>(null);
    const [confirmingDelete, setConfirmingDelete] = useState(false);

    useEffect(() => {
        if (!expanded || detail) return;
        let canceled = false;
        void fetchQaHistoryDetail(entry.id).then((d) => {
            if (!canceled) setDetail(d);
        });
        return () => {
            canceled = true;
        };
    }, [expanded, detail, entry.id]);

    return (
        <li className="border border-gray-200 dark:border-gray-700 rounded-md bg-white dark:bg-gray-800 overflow-hidden">
            <button
                onClick={() => setExpanded((e) => !e)}
                className="w-full px-3 py-2 flex items-start gap-2 text-left hover:bg-gray-50 dark:hover:bg-gray-700/50"
            >
                {expanded ? (
                    <ChevronDown className="w-4 h-4 mt-0.5 flex-shrink-0 text-gray-500" />
                ) : (
                    <ChevronRight className="w-4 h-4 mt-0.5 flex-shrink-0 text-gray-500" />
                )}
                <div className="min-w-0 flex-1">
                    <div className="text-sm text-gray-900 dark:text-gray-100 line-clamp-1">
                        {entry.question}
                    </div>
                    <div className="flex gap-2 mt-0.5 text-xs text-gray-500 dark:text-gray-400">
                        <span>{entry.asked_at?.replace('T', ' ').slice(0, 16)}</span>
                        <span>·</span>
                        <span>{scopeLabel(entry)}</span>
                        {entry.done_reason && entry.done_reason !== 'stop' && (
                            <>
                                <span>·</span>
                                <span className="text-amber-600 dark:text-amber-400">
                                    {entry.done_reason}
                                </span>
                            </>
                        )}
                    </div>
                </div>
            </button>
            {expanded && (
                <div className="px-3 pb-3 space-y-2 border-t border-gray-100 dark:border-gray-700">
                    {detail ? (
                        <>
                            <div className="mt-2">
                                <div className="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-1">
                                    回答
                                </div>
                                <div className="text-sm text-gray-800 dark:text-gray-200 whitespace-pre-wrap leading-relaxed">
                                    {detail.answer || (
                                        <span className="text-gray-400">（応答なし）</span>
                                    )}
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
                                                    onClick={() =>
                                                        onOpenImage(c.book_name, c.page_no)
                                                    }
                                                    className="text-xs px-2 py-0.5 rounded border border-gray-300 dark:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-200"
                                                >
                                                    {c.book_name} p{c.page_no}
                                                </button>
                                            </li>
                                        ))}
                                    </ul>
                                </div>
                            )}
                            <div className="flex justify-end pt-1">
                                <button
                                    onClick={() => setConfirmingDelete(true)}
                                    className="text-xs px-2 py-1 rounded text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/30 flex items-center gap-1"
                                >
                                    <Trash2 className="w-3 h-3" />
                                    削除
                                </button>
                            </div>
                        </>
                    ) : (
                        <p className="text-xs text-gray-500 mt-2">読み込み中…</p>
                    )}
                </div>
            )}
            <ConfirmDialog
                open={confirmingDelete}
                title="この履歴を削除しますか?"
                message="削除後は復元できません。"
                confirmLabel="削除"
                danger
                onConfirm={() => {
                    setConfirmingDelete(false);
                    onDelete(entry.id);
                }}
                onCancel={() => setConfirmingDelete(false)}
            />
        </li>
    );
}
