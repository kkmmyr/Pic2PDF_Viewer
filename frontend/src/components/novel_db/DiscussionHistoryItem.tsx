/**
 * 読書会 番組台本履歴アイテム（折りたたみカード）。
 * NovelDiscussionPage / NovelDetailPage の両方から利用する。
 *
 * - format_version=2: セグメント見出し付き表示 + 機械チェックバッジ + エクスポート
 * - format_version=1: 従来のフラット表示（セグメント区切りなし）
 */
import { useMemo, useState } from 'react';
import { ChevronDown, ChevronUp, Trash2, Users } from 'lucide-react';

import ScriptView, { ChecksBadge, ScriptExportButtons } from '@/components/novel_db/script-view';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import type { DiscussionHistoryItem } from '@/features/novel_db/api';
import { SPEAKER_NAMES } from '@/features/novel_db/script-export';
import { formatSqliteUtcAsJst } from '@/utils/date';

interface Props {
    item: DiscussionHistoryItem;
    /** エクスポート（コピー / MD）に使う書籍名。省略時はエクスポートボタン非表示。 */
    bookName?: string;
    /** 指定時のみ削除ボタン（ゴミ箱）を表示する。確認ダイアログは本カードが出す。 */
    onDelete?: (filename: string) => void | Promise<void>;
}

export default function DiscussionHistoryItemCard({ item, bookName, onDelete }: Props) {
    const [open, setOpen] = useState(false);
    const [confirmingDelete, setConfirmingDelete] = useState(false);

    const isV2 = item.format_version === 2;
    const nameA = item.personas[0]?.name ?? SPEAKER_NAMES.A;
    const nameB = item.personas[1]?.name ?? SPEAKER_NAMES.B;
    const dateStr = item.created_at ? formatSqliteUtcAsJst(item.created_at) : '';

    /** セグメント id → 見出しタイトルのマップ（v2 のみ）。 */
    const segmentTitles = useMemo(() => {
        const map: Record<string, string> = {};
        for (const seg of item.segments ?? []) map[seg.id] = seg.title;
        return map;
    }, [item.segments]);

    return (
        <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
            <div className="flex items-center bg-gray-50 dark:bg-gray-800">
                <button
                    type="button"
                    onClick={() => setOpen((v) => !v)}
                    className="flex-1 flex items-center justify-between px-3 py-2 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
                >
                    <div className="flex items-center gap-2 text-sm">
                        <Users className="w-3.5 h-3.5 text-gray-400" />
                        <span className="font-medium text-gray-800 dark:text-gray-200">
                            {`${nameA} × ${nameB}`}
                        </span>
                        <span className="text-xs text-gray-400">（{item.turn_count} ターン）</span>
                        {dateStr && <span className="text-xs text-gray-400">{dateStr}</span>}
                        {isV2 && item.checks && <ChecksBadge checks={item.checks} />}
                    </div>
                    {open ? (
                        <ChevronUp className="w-4 h-4 text-gray-400" />
                    ) : (
                        <ChevronDown className="w-4 h-4 text-gray-400" />
                    )}
                </button>
                {onDelete && (
                    <button
                        type="button"
                        onClick={() => setConfirmingDelete(true)}
                        aria-label="台本を削除"
                        title="台本を削除"
                        className="px-3 py-2 text-gray-400 hover:text-red-600 dark:hover:text-red-400 transition-colors"
                    >
                        <Trash2 className="w-4 h-4" />
                    </button>
                )}
            </div>
            {open && (
                <div className="px-3 py-3 space-y-3">
                    <ScriptView
                        turns={item.turns}
                        segments={isV2 ? segmentTitles : null}
                        nameA={nameA}
                        nameB={nameB}
                    />
                    {bookName && (
                        <div className="pt-1 border-t border-gray-100 dark:border-gray-700/50">
                            <div className="pt-2">
                                <ScriptExportButtons
                                    bookName={bookName}
                                    turns={item.turns}
                                    segments={isV2 ? segmentTitles : null}
                                    createdAt={dateStr || item.created_at}
                                />
                            </div>
                        </div>
                    )}
                </div>
            )}
            {onDelete && (
                <ConfirmDialog
                    open={confirmingDelete}
                    title="台本の削除"
                    message={`この台本を削除しますか？\n${dateStr || item.filename}`}
                    confirmLabel="削除"
                    danger
                    onConfirm={() => {
                        setConfirmingDelete(false);
                        void onDelete(item.filename);
                    }}
                    onCancel={() => setConfirmingDelete(false)}
                />
            )}
        </div>
    );
}
