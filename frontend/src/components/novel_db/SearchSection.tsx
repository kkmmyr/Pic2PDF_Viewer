/**
 * 検索セクション。検索ボックス + 結果リスト + 無限スクロール。
 */
import { useEffect, useRef } from 'react';
import { Search } from 'lucide-react';

import type { BookSummary, Scope, SeriesSummary } from '../../features/novel_db/types';
import { useNovelDbSearch } from '../../hooks/novel_db';

import SearchHitItem from './SearchHitItem';

interface Props {
    scope: Scope;
    onOpenImage: (book: string, pageNo: number) => void;
    disabled?: boolean;
    /** スコープラベル表示用（任意） */
    books?: BookSummary[];
    series?: SeriesSummary[];
}

export default function SearchSection({ scope, onOpenImage, disabled }: Props) {
    const { query, setQuery, hits, total, hasMore, isSearching, error, loadMore } =
        useNovelDbSearch(scope);
    const sentinelRef = useRef<HTMLDivElement | null>(null);

    // IntersectionObserver で末端到達検知 → loadMore
    useEffect(() => {
        if (!sentinelRef.current || !hasMore) return;
        const target = sentinelRef.current;
        const observer = new IntersectionObserver(
            (entries) => {
                if (entries.some((e) => e.isIntersecting)) {
                    void loadMore();
                }
            },
            { rootMargin: '200px' },
        );
        observer.observe(target);
        return () => observer.disconnect();
    }, [hasMore, loadMore]);

    return (
        <section className="space-y-3">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">検索</h2>
            <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                <input
                    type="search"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="キーワードを入力…"
                    disabled={disabled}
                    className="w-full pl-9 pr-3 py-2 text-sm rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50"
                />
            </div>
            {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
            {query.trim() === '' ? (
                <p className="text-sm text-gray-500">
                    キーワードを入力して検索を開始してください。
                </p>
            ) : isSearching && hits.length === 0 ? (
                <p className="text-sm text-gray-500">検索中…</p>
            ) : hits.length === 0 ? (
                <p className="text-sm text-gray-500">該当する結果がありません。</p>
            ) : (
                <>
                    <p className="text-xs text-gray-500">
                        {total} 件中 {hits.length} 件を表示
                    </p>
                    <div className="space-y-2">
                        {hits.map((h) => (
                            <SearchHitItem
                                key={`${h.book_name}-${h.page_no}-${h.rrf_score}`}
                                hit={h}
                                onOpenImage={onOpenImage}
                            />
                        ))}
                    </div>
                    {hasMore && (
                        <div ref={sentinelRef} className="py-4 text-center text-xs text-gray-400">
                            {isSearching ? '読み込み中…' : 'スクロールで続きを読み込み'}
                        </div>
                    )}
                </>
            )}
        </section>
    );
}
