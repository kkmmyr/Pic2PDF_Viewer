import { useState } from 'react';
import { Trash2 } from 'lucide-react';

import type { QaHistoryEntry } from '../../features/novel_db/types';
import { ConfirmDialog } from '../ui/ConfirmDialog';

interface Props {
    entry: QaHistoryEntry;
    isActive: boolean;
    onSelect: (id: number) => void;
    onDelete: (id: number) => void;
}

function scopeLabel(entry: QaHistoryEntry): string {
    if (entry.scope.type === 'all') return '全件';
    if (entry.scope.type === 'series') return `シリーズ: ${entry.scope.id ?? ''}`;
    return `単冊: ${entry.scope.id ?? ''}`;
}

export default function QuestionHistoryItem({ entry, isActive, onSelect, onDelete }: Props) {
    const [confirmingDelete, setConfirmingDelete] = useState(false);

    return (
        <li
            className={`group relative border-b border-gray-200 dark:border-gray-700 ${isActive ? 'bg-primary-50 dark:bg-primary-900/30' : ''}`}
        >
            <button
                type="button"
                onClick={() => onSelect(entry.id)}
                className="w-full text-left px-3 py-2 hover:bg-gray-100 dark:hover:bg-gray-800"
            >
                <div
                    className="text-xs font-medium text-gray-900 dark:text-gray-100 truncate pr-6"
                    title={entry.question}
                >
                    {entry.question}
                </div>
                <div className="text-[10px] text-gray-500 dark:text-gray-400 truncate">
                    {scopeLabel(entry)}
                </div>
            </button>
            <button
                type="button"
                onClick={() => setConfirmingDelete(true)}
                title="削除"
                className="opacity-0 group-hover:opacity-100 absolute right-1 top-1.5 p-1 text-gray-500 hover:text-red-600"
            >
                <Trash2 className="w-3.5 h-3.5" />
            </button>
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
