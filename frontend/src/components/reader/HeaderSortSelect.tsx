import { ArrowUpDown } from 'lucide-react';
import type { SortOrder } from '../../types';

const SORT_OPTIONS: { value: SortOrder; label: string }[] = [
    { value: 'name_asc',        label: '名前 (A→Z)' },
    { value: 'name_desc',       label: '名前 (Z→A)' },
    { value: 'date_desc',       label: '新しい順' },
    { value: 'date_asc',        label: '古い順' },
    { value: 'favorites_first', label: 'お気に入り優先' },
    { value: 'view_desc',       label: 'よく見る順' },
    { value: 'recent_view',     label: '最近見た順' },
];

interface HeaderSortSelectProps {
    sortOrder: SortOrder;
    onSortChange: (order: SortOrder) => void;
}

export function HeaderSortSelect({ sortOrder, onSortChange }: HeaderSortSelectProps) {
    return (
        <div className="flex items-center gap-1 text-sm text-gray-600 dark:text-gray-400">
            <ArrowUpDown className="w-4 h-4 text-gray-400 dark:text-gray-500 shrink-0" />
            <select
                value={sortOrder}
                onChange={(e) => onSortChange(e.target.value as SortOrder)}
                className="border border-gray-200 dark:border-gray-600 rounded-md px-2 py-1 text-sm text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-400"
            >
                {SORT_OPTIONS.map(opt => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
            </select>
        </div>
    );
}
