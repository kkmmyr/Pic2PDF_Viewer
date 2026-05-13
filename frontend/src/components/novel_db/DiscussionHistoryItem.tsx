/**
 * 読書会ディスカッション履歴アイテム（折りたたみカード）。
 * NovelDiscussionPage / NovelDetailPage の両方から利用する。
 */
import { useState } from 'react';
import { ChevronDown, ChevronUp, Users } from 'lucide-react';

import type { DiscussionHistoryItem } from '../../features/novel_db/api';
import { formatSqliteUtcAsJst } from '../../utils/date';

interface TurnCardProps {
    speaker: 'A' | 'B';
    text: string;
    nameA: string;
    nameB: string;
}

export function TurnCard({ speaker, text, nameA, nameB }: TurnCardProps) {
    const isA = speaker === 'A';
    return (
        <div className={`flex gap-2.5 ${isA ? '' : 'flex-row-reverse'}`}>
            <div
                className={`w-8 h-8 shrink-0 rounded-full flex items-center justify-center text-xs font-bold text-white ${
                    isA ? 'bg-indigo-500' : 'bg-emerald-500'
                }`}
            >
                {speaker}
            </div>
            <div
                className={`flex-1 max-w-[85%] rounded-xl px-3.5 py-2.5 text-sm leading-relaxed ${
                    isA
                        ? 'bg-indigo-50 dark:bg-indigo-900/30 text-indigo-900 dark:text-indigo-100 rounded-tl-sm'
                        : 'bg-emerald-50 dark:bg-emerald-900/30 text-emerald-900 dark:text-emerald-100 rounded-tr-sm'
                }`}
            >
                <p className="text-xs font-medium mb-1 opacity-70">{isA ? nameA : nameB}</p>
                <p className="whitespace-pre-wrap">{text}</p>
            </div>
        </div>
    );
}

interface Props {
    item: DiscussionHistoryItem;
}

export default function DiscussionHistoryItemCard({ item }: Props) {
    const [open, setOpen] = useState(false);
    const nameA = item.personas[0]?.name ?? 'A';
    const nameB = item.personas[1]?.name ?? 'B';
    const dateStr = item.created_at ? formatSqliteUtcAsJst(item.created_at) : '';

    return (
        <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
            <button
                type="button"
                onClick={() => setOpen((v) => !v)}
                className="w-full flex items-center justify-between px-3 py-2 bg-gray-50 dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
            >
                <div className="flex items-center gap-2 text-sm">
                    <Users className="w-3.5 h-3.5 text-gray-400" />
                    <span className="font-medium text-gray-800 dark:text-gray-200">
                        {nameA} × {nameB}
                    </span>
                    <span className="text-xs text-gray-400">（{item.turn_count} ターン）</span>
                    {dateStr && <span className="text-xs text-gray-400">{dateStr}</span>}
                </div>
                {open ? (
                    <ChevronUp className="w-4 h-4 text-gray-400" />
                ) : (
                    <ChevronDown className="w-4 h-4 text-gray-400" />
                )}
            </button>
            {open && (
                <div className="px-3 py-3 space-y-3">
                    {item.turns.map((t, i) => (
                        <TurnCard
                            key={i}
                            speaker={t.speaker as 'A' | 'B'}
                            text={t.text}
                            nameA={nameA}
                            nameB={nameB}
                        />
                    ))}
                </div>
            )}
        </div>
    );
}
