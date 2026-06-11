/**
 * 検索 / 質問のスコープ切替ドロップダウン。
 * 全件 / シリーズ / 単冊 を選択できる。
 * シリーズ未所属書籍は「シリーズ」グループには含めない（要件 TBD-7）。
 */
import type { BookSummary, Scope, SeriesSummary } from '@/features/novel_db/types';

interface Props {
    scope: Scope;
    onChange: (next: Scope) => void;
    books: BookSummary[];
    series: SeriesSummary[];
}

type Option =
    | { kind: 'all' }
    | { kind: 'series'; id: string; label: string }
    | { kind: 'book'; name: string; label: string };

function encodeOption(opt: Option): string {
    if (opt.kind === 'all') return 'all';
    if (opt.kind === 'series') return `series:${opt.id}`;
    return `book:${opt.name}`;
}

function decodeOption(value: string): Option {
    if (value === 'all') return { kind: 'all' };
    const [kind, ...rest] = value.split(':');
    const id = rest.join(':');
    if (kind === 'series') return { kind: 'series', id, label: id };
    if (kind === 'book') return { kind: 'book', name: id, label: id };
    return { kind: 'all' };
}

function scopeToValue(scope: Scope): string {
    if (scope.type === 'series' && scope.id) return `series:${scope.id}`;
    if (scope.type === 'book' && scope.id) return `book:${scope.id}`;
    return 'all';
}

export default function ScopeSelector({ scope, onChange, books, series }: Props) {
    const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
        const opt = decodeOption(e.target.value);
        if (opt.kind === 'all') {
            onChange({ type: 'all' });
        } else if (opt.kind === 'series') {
            onChange({ type: 'series', id: opt.id });
        } else {
            onChange({ type: 'book', id: opt.name });
        }
    };

    return (
        <div className="flex items-center gap-2">
            <label htmlFor="novel-db-scope" className="text-sm text-gray-600 dark:text-gray-400">
                スコープ:
            </label>
            <select
                id="novel-db-scope"
                value={scopeToValue(scope)}
                onChange={handleChange}
                className="px-3 py-1.5 text-sm rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-primary-500 min-w-[200px]"
            >
                <option value={encodeOption({ kind: 'all' })}>全件 ({books.length} 冊)</option>
                {series.length > 0 && (
                    <optgroup label="シリーズ">
                        {series.map((s) => (
                            <option
                                key={s.id}
                                value={encodeOption({
                                    kind: 'series',
                                    id: s.id,
                                    label: s.name,
                                })}
                            >
                                {s.name} ({s.book_count} 冊)
                            </option>
                        ))}
                    </optgroup>
                )}
                <optgroup label="単冊">
                    {books.map((b) => (
                        <option
                            key={b.name}
                            value={encodeOption({
                                kind: 'book',
                                name: b.name,
                                label: b.name,
                            })}
                        >
                            {b.name}
                        </option>
                    ))}
                </optgroup>
            </select>
        </div>
    );
}
