import { ArrowUpDown } from 'lucide-react';
import type { SortOrder } from '@/types';
import { cn } from '@/lib/utils';

const SORT_OPTIONS: { value: SortOrder; label: string }[] = [
    { value: 'name_asc', label: '名前 (A→Z)' },
    { value: 'name_desc', label: '名前 (Z→A)' },
    { value: 'date_desc', label: '新しい順' },
    { value: 'date_asc', label: '古い順' },
    { value: 'favorites_first', label: 'お気に入り優先' },
    { value: 'view_desc', label: 'よく見る順' },
    { value: 'recent_view', label: '最近見た順' },
];

interface HeaderSortSelectProps {
    sortOrder: SortOrder;
    onSortChange: (order: SortOrder) => void;
    className?: string;
    compact?: boolean;
}

export function HeaderSortSelect({
    sortOrder,
    onSortChange,
    className,
    compact = false,
}: HeaderSortSelectProps) {
    return (
        <div
            className={cn(
                'flex min-w-0 items-center gap-1 text-sm text-gray-700 dark:text-gray-300',
                className,
            )}
        >
            {!compact && (
                <ArrowUpDown className="h-4 w-4 shrink-0 text-gray-500 dark:text-gray-400" />
            )}
            <select
                value={sortOrder}
                onChange={(e) => onSortChange(e.target.value as SortOrder)}
                aria-label="並び替え"
                className="min-h-11 min-w-0 flex-1 rounded-md border border-gray-300 bg-white px-2 py-2 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-primary-500 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-300 lg:min-h-9 lg:py-1.5"
            >
                {SORT_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                        {opt.label}
                    </option>
                ))}
            </select>
        </div>
    );
}
