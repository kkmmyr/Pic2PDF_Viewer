import { type FormEvent, useEffect, useMemo, useState } from 'react';
import { ChevronLeft, ChevronRight, Database, Loader2, Search } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';

import { KindleBookDetailDialog } from '@/components/kindle/KindleBookDetailDialog';
import { KindlePageShell } from '@/components/kindle/KindlePageShell';
import { bookTypeLabel, CAPTURE_LABELS, OWNERSHIP_LABELS } from '@/components/kindle/kindle-labels';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import {
    clearKindleCatalogFilters,
    KINDLE_CATALOG_PAGE_SIZE_OPTIONS,
    parseKindleCatalogQuery,
    replaceKindleCatalogParam,
} from '@/features/kindle/catalog-query';
import { useKindleBooks } from '@/hooks/useKindleCatalog';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import type { KindleCatalogBook, KindleCatalogFilters } from '@/types/kindleCatalog';
import { errorMessage } from '@/utils/error';

function StatusPill({ children, tone = 'gray' }: { children: string; tone?: 'blue' | 'gray' }) {
    const toneClass =
        tone === 'blue'
            ? 'bg-primary-50 text-primary-700 dark:bg-primary-900/30 dark:text-primary-300'
            : 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300';
    return <span className={`rounded-full px-2 py-1 text-xs ${toneClass}`}>{children}</span>;
}

function KindleBookRow({
    book,
    onOpen,
}: {
    book: KindleCatalogBook;
    onOpen: (book: KindleCatalogBook) => void;
}) {
    const authorLabel = book.authors.join(' / ') || '—';

    return (
        <tr className="border-b border-gray-100 align-top last:border-0 dark:border-gray-800">
            <td className="px-4 py-3">
                <button
                    type="button"
                    className="text-left font-medium text-gray-900 hover:text-primary-700 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 dark:text-gray-100 dark:hover:text-primary-300"
                    onClick={() => onOpen(book)}
                >
                    {book.title}
                </button>
                <div className="mt-1 font-mono text-xs text-gray-400">{book.asin}</div>
                <div
                    className="mt-1 truncate text-xs text-gray-500 dark:text-gray-400 lg:hidden"
                    title={`著者：${authorLabel}`}
                >
                    著者：{authorLabel}
                </div>
                <div className="mt-2 flex flex-wrap gap-1.5 lg:hidden">
                    <StatusPill tone="blue">{bookTypeLabel(book.book_type)}</StatusPill>
                    <StatusPill>{OWNERSHIP_LABELS[book.ownership]}</StatusPill>
                    <StatusPill>{CAPTURE_LABELS[book.capture_state]}</StatusPill>
                </div>
            </td>
            <td className="hidden px-4 py-3 text-sm text-gray-600 dark:text-gray-300 lg:table-cell">
                {authorLabel}
            </td>
            <td className="hidden px-4 py-3 text-sm lg:table-cell">
                {bookTypeLabel(book.book_type)}
            </td>
            <td className="hidden px-4 py-3 lg:table-cell">
                <StatusPill tone="blue">{OWNERSHIP_LABELS[book.ownership]}</StatusPill>
            </td>
            <td className="hidden px-4 py-3 lg:table-cell">
                <StatusPill>{CAPTURE_LABELS[book.capture_state]}</StatusPill>
            </td>
        </tr>
    );
}

export default function KindleCatalogPage() {
    const [searchParams, setSearchParams] = useSearchParams();
    const parsedQuery = useMemo(() => parseKindleCatalogQuery(searchParams), [searchParams]);
    const { q: urlQuery, pageSize, page, bookType, ownership, captureState } = parsedQuery;
    const [queryInput, setQueryInput] = useState(urlQuery);
    const [selectedBook, setSelectedBook] = useState<KindleCatalogBook | null>(null);
    const debouncedQuery = useDebouncedValue(queryInput, 300);

    const filters = useMemo<KindleCatalogFilters>(
        () => ({
            q: urlQuery,
            bookType,
            ownership,
            captureState,
            page,
            pageSize,
        }),
        [bookType, captureState, ownership, page, pageSize, urlQuery],
    );
    const books = useKindleBooks(filters);

    useEffect(() => {
        setQueryInput(urlQuery);
    }, [urlQuery]);

    useEffect(() => {
        if (debouncedQuery.trim() === urlQuery) return;
        setSearchParams(
            (current) => replaceKindleCatalogParam(current, 'q', debouncedQuery.trim()),
            {
                replace: true,
            },
        );
    }, [debouncedQuery, setSearchParams, urlQuery]);

    const submitSearch = (event: FormEvent) => {
        event.preventDefault();
        setSearchParams((current) => replaceKindleCatalogParam(current, 'q', queryInput.trim()), {
            replace: true,
        });
    };

    const totalPages = Math.max(1, Math.ceil((books.data?.total ?? 0) / pageSize));
    const visiblePage = Math.min(page, totalPages);

    const updateParam = (key: string, value: string) => {
        setSearchParams((current) => replaceKindleCatalogParam(current, key, value), {
            replace: true,
        });
    };

    const setPage = (nextPage: number) => {
        setSearchParams(
            (current) => replaceKindleCatalogParam(current, 'page', String(nextPage), false),
            { replace: true },
        );
    };

    const clearFilters = () => {
        setQueryInput('');
        setSearchParams(clearKindleCatalogFilters);
    };

    const hasFilters = Boolean(urlQuery || bookType || ownership || captureState);

    return (
        <KindlePageShell title="Kindle 購入書籍" description="購入・借用カタログから本を検索します">
            <form
                onSubmit={submitSearch}
                className="grid gap-3 rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-900 md:grid-cols-2 xl:grid-cols-[minmax(280px,1fr)_160px_170px_170px_auto]"
            >
                <label className="relative md:col-span-2 xl:col-span-1">
                    <span className="sr-only">タイトル・ASIN・著者を検索</span>
                    <Search className="absolute left-3 top-2.5 h-4 w-4 text-gray-400" />
                    <input
                        value={queryInput}
                        onChange={(event) => setQueryInput(event.target.value)}
                        placeholder="タイトル・ASIN・著者を検索"
                        className="w-full rounded-lg border border-gray-300 bg-white py-2 pl-9 pr-3 text-sm focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-500/20 dark:border-gray-600 dark:bg-gray-800"
                    />
                </label>
                <select
                    aria-label="書籍種別"
                    value={bookType}
                    onChange={(event) => updateParam('book_type', event.target.value)}
                    className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800"
                >
                    <option value="">全種別</option>
                    <option value="comic">漫画</option>
                    <option value="novel">小説</option>
                    <option value="other">その他</option>
                    <option value="unknown">未分類</option>
                </select>
                <select
                    aria-label="所有状態"
                    value={ownership}
                    onChange={(event) => updateParam('ownership', event.target.value)}
                    className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800"
                >
                    <option value="">全所有状態</option>
                    <option value="purchased">購入</option>
                    <option value="borrowed_active">KU借用中</option>
                    <option value="borrowed_ended">KU終了</option>
                    <option value="returned">返品</option>
                    <option value="unknown">不明</option>
                </select>
                <select
                    aria-label="画像取込状態"
                    value={captureState}
                    onChange={(event) => updateParam('capture_state', event.target.value)}
                    className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800"
                >
                    <option value="">全画像状態</option>
                    <option value="not_captured">画像なし</option>
                    <option value="captured">取込済み</option>
                    <option value="multiple_links">重複確認</option>
                    <option value="capture_pending">取込中</option>
                </select>
                <Button
                    variant="secondary"
                    onClick={clearFilters}
                    disabled={!hasFilters}
                    className="min-h-10"
                >
                    条件をクリア
                </Button>
            </form>

            {books.error && (
                <Alert variant="error" className="mt-4">
                    {errorMessage(books.error, 'カタログを取得できませんでした')}
                </Alert>
            )}

            <div
                className="mt-4 overflow-hidden rounded-xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900"
                aria-busy={books.isFetching}
            >
                {books.isLoading ? (
                    <div className="flex items-center justify-center gap-2 py-20 text-sm text-gray-500">
                        <Loader2 className="h-5 w-5 animate-spin" />
                        購入書籍を読み込み中
                    </div>
                ) : (
                    <>
                        {books.isFetching && (
                            <div className="flex items-center gap-2 border-b border-gray-200 bg-primary-50 px-4 py-2 text-xs text-primary-700 dark:border-gray-700 dark:bg-primary-900/20 dark:text-primary-300">
                                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                検索結果を更新中
                            </div>
                        )}
                        <div className="overflow-x-auto">
                            <table className="w-full">
                                <thead className="bg-gray-50 text-left text-xs text-gray-500 dark:bg-gray-800/70 dark:text-gray-400">
                                    <tr>
                                        <th className="px-4 py-3">書籍</th>
                                        <th className="hidden px-4 py-3 lg:table-cell">著者</th>
                                        <th className="hidden px-4 py-3 lg:table-cell">種別</th>
                                        <th className="hidden px-4 py-3 lg:table-cell">所有</th>
                                        <th className="hidden px-4 py-3 lg:table-cell">画像</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {books.data?.items.map((book) => (
                                        <KindleBookRow
                                            key={book.asin}
                                            book={book}
                                            onOpen={setSelectedBook}
                                        />
                                    ))}
                                </tbody>
                            </table>
                        </div>
                        {(books.data?.items.length ?? 0) === 0 && (
                            <div className="flex flex-col items-center py-16 text-gray-500">
                                <Database className="mb-2 h-8 w-8" />
                                <p>該当する書籍はありません</p>
                                {hasFilters && (
                                    <Button variant="ghost" className="mt-2" onClick={clearFilters}>
                                        検索条件を解除
                                    </Button>
                                )}
                            </div>
                        )}
                    </>
                )}

                <div className="flex flex-wrap items-center justify-between gap-3 border-t border-gray-200 px-4 py-3 text-sm dark:border-gray-700">
                    <div className="flex items-center gap-3">
                        <span>{(books.data?.total ?? 0).toLocaleString()} 件</span>
                        <label className="flex items-center gap-2 text-gray-500 dark:text-gray-400">
                            表示件数
                            <select
                                aria-label="表示件数"
                                value={pageSize}
                                onChange={(event) => updateParam('page_size', event.target.value)}
                                className="rounded border border-gray-300 bg-white px-2 py-1 dark:border-gray-600 dark:bg-gray-800"
                            >
                                {KINDLE_CATALOG_PAGE_SIZE_OPTIONS.map((option) => (
                                    <option key={option} value={option}>
                                        {option}
                                    </option>
                                ))}
                            </select>
                        </label>
                    </div>
                    <div className="flex items-center gap-2">
                        <Button
                            variant="ghost"
                            size="sm"
                            aria-label="前のページ"
                            disabled={visiblePage <= 1}
                            onClick={() => setPage(visiblePage - 1)}
                        >
                            <ChevronLeft className="h-5 w-5" />
                        </Button>
                        <span>
                            {visiblePage} / {totalPages}
                        </span>
                        <Button
                            variant="ghost"
                            size="sm"
                            aria-label="次のページ"
                            disabled={visiblePage >= totalPages}
                            onClick={() => setPage(visiblePage + 1)}
                        >
                            <ChevronRight className="h-5 w-5" />
                        </Button>
                    </div>
                </div>
            </div>

            <KindleBookDetailDialog book={selectedBook} onClose={() => setSelectedBook(null)} />
        </KindlePageShell>
    );
}
