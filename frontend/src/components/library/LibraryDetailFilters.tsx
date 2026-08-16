import { BookOpen, Library, User } from 'lucide-react';
import type { ReadState } from '@/types';
import type { GroupMode } from '@/hooks/library/useLibraryGrouping';
import { SearchableSelect } from '@/components/ui/searchable-select';
import { cn } from '@/lib/utils';

type ReadStateFilter = '' | ReadState;

interface LibraryDetailFiltersProps {
    authorFilter: string;
    allAuthors: string[];
    groupMode: GroupMode;
    readStateFilter: ReadStateFilter;
    hideAuthorSelect: boolean;
    layout: 'inline' | 'stacked';
    onAuthorFilterChange: (author: string) => void;
    onGroupModeChange: (mode: GroupMode) => void;
    onReadStateFilterChange: (value: ReadStateFilter) => void;
}

const selectClassName =
    'min-h-11 w-full rounded-md border border-gray-300 bg-white px-2 py-2 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-primary-500 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-300 lg:min-h-9 lg:py-1.5';

export function LibraryDetailFilters({
    authorFilter,
    allAuthors,
    groupMode,
    readStateFilter,
    hideAuthorSelect,
    layout,
    onAuthorFilterChange,
    onGroupModeChange,
    onReadStateFilterChange,
}: LibraryDetailFiltersProps) {
    const stacked = layout === 'stacked';

    return (
        <div className={cn(stacked ? 'space-y-4' : 'flex flex-wrap items-center gap-3')}>
            {allAuthors.length > 0 && !hideAuthorSelect && (
                <label
                    className={cn(
                        'text-sm text-gray-700 dark:text-gray-300',
                        stacked ? 'block' : 'flex items-center gap-1',
                    )}
                >
                    <span
                        className={cn('flex items-center gap-2', stacked && 'mb-1.5 font-medium')}
                    >
                        <User className="h-4 w-4 shrink-0 text-gray-500 dark:text-gray-400" />
                        {stacked ? '作者' : <span className="sr-only">作者</span>}
                    </span>
                    <SearchableSelect
                        value={authorFilter}
                        options={allAuthors}
                        emptyLabel="作者: すべて"
                        placeholder="作者名で絞り込み"
                        onChange={onAuthorFilterChange}
                        className={stacked ? 'w-full' : 'w-48'}
                    />
                </label>
            )}

            <label
                className={cn(
                    'text-sm text-gray-700 dark:text-gray-300',
                    stacked ? 'block' : 'flex items-center gap-1',
                )}
            >
                <span className={cn('flex items-center gap-2', stacked && 'mb-1.5 font-medium')}>
                    <Library className="h-4 w-4 shrink-0 text-gray-500 dark:text-gray-400" />
                    {stacked ? '表示方法' : <span className="sr-only">表示方法</span>}
                </span>
                <select
                    value={groupMode}
                    onChange={(e) => onGroupModeChange(e.target.value as GroupMode)}
                    aria-label="表示方法"
                    className={cn(selectClassName, !stacked && 'max-w-40')}
                >
                    <option value="none">グループ化なし</option>
                    <option value="series">シリーズで</option>
                    <option value="author">作者で</option>
                    <option value="author-then-series">作者 → シリーズで</option>
                </select>
            </label>

            <label
                className={cn(
                    'text-sm text-gray-700 dark:text-gray-300',
                    stacked ? 'block' : 'flex items-center gap-1',
                )}
            >
                <span className={cn('flex items-center gap-2', stacked && 'mb-1.5 font-medium')}>
                    <BookOpen className="h-4 w-4 shrink-0 text-gray-500 dark:text-gray-400" />
                    {stacked ? '読書状態' : <span className="sr-only">読書状態</span>}
                </span>
                <select
                    value={readStateFilter}
                    onChange={(e) => onReadStateFilterChange(e.target.value as ReadStateFilter)}
                    aria-label="読書状態"
                    className={selectClassName}
                >
                    <option value="">読書状態すべて</option>
                    <option value="unread">未読のみ</option>
                    <option value="reading">読書中のみ</option>
                    <option value="done">読了のみ</option>
                </select>
            </label>
        </div>
    );
}
