/**
 * ハイブリッド検索フック（debounce 300ms + 無限スクロール）。
 *
 * - `query` 変更を debounce してから検索開始
 * - 結果は `hits` に蓄積、`loadMore()` で次の 20 件を追加読み込み
 * - `scope` 変更時は結果をリセットして先頭から取り直す
 */
import { useCallback, useEffect, useRef, useState } from 'react';

import { searchHits } from '../../features/novel_db/api';
import type { Scope, SearchHit } from '../../features/novel_db/types';
import { NOVEL_DB_CONFIG } from '../../constants';

export interface UseNovelDbSearch {
    query: string;
    setQuery: (q: string) => void;
    hits: SearchHit[];
    total: number;
    hasMore: boolean;
    isSearching: boolean;
    error: string | null;
    loadMore: () => Promise<void>;
}

export function useNovelDbSearch(scope: Scope): UseNovelDbSearch {
    const [query, setQuery] = useState('');
    const [debouncedQuery, setDebouncedQuery] = useState('');
    const [hits, setHits] = useState<SearchHit[]>([]);
    const [total, setTotal] = useState(0);
    const [isSearching, setIsSearching] = useState(false);
    const [error, setError] = useState<string | null>(null);
    // 古いリクエストの結果が遅れて到着した場合に setHits しないためのカウンタ
    const requestIdRef = useRef(0);

    // debounce
    useEffect(() => {
        const t = setTimeout(() => setDebouncedQuery(query), NOVEL_DB_CONFIG.SEARCH_DEBOUNCE_MS);
        return () => clearTimeout(t);
    }, [query]);

    // 初回 / scope 変更 / debouncedQuery 変更で先頭から検索
    useEffect(() => {
        const trimmed = debouncedQuery.trim();
        if (!trimmed) {
            setHits([]);
            setTotal(0);
            setError(null);
            return;
        }
        const reqId = ++requestIdRef.current;
        setIsSearching(true);
        setError(null);
        void searchHits({
            query: trimmed,
            scope,
            offset: 0,
            limit: NOVEL_DB_CONFIG.SEARCH_PAGE_SIZE,
        })
            .then((res) => {
                if (reqId !== requestIdRef.current) return;
                setHits(res.hits);
                setTotal(res.total);
            })
            .catch((e: unknown) => {
                if (reqId !== requestIdRef.current) return;
                setError(e instanceof Error ? e.message : String(e));
            })
            .finally(() => {
                if (reqId !== requestIdRef.current) return;
                setIsSearching(false);
            });
    }, [debouncedQuery, scope]);

    const loadMore = useCallback(async () => {
        const trimmed = debouncedQuery.trim();
        if (!trimmed || isSearching || hits.length >= total) return;
        const reqId = ++requestIdRef.current;
        setIsSearching(true);
        try {
            const res = await searchHits({
                query: trimmed,
                scope,
                offset: hits.length,
                limit: NOVEL_DB_CONFIG.SEARCH_PAGE_SIZE,
            });
            if (reqId !== requestIdRef.current) return;
            setHits((prev) => [...prev, ...res.hits]);
            setTotal(res.total);
        } catch (e) {
            if (reqId !== requestIdRef.current) return;
            setError(e instanceof Error ? e.message : String(e));
        } finally {
            // 古いリクエストの結果は捨てるため、最新リクエストのときのみ状態更新
            if (reqId === requestIdRef.current) {
                setIsSearching(false);
            }
        }
    }, [debouncedQuery, scope, hits.length, total, isSearching]);

    return {
        query,
        setQuery,
        hits,
        total,
        hasMore: hits.length < total,
        isSearching,
        error,
        loadMore,
    };
}
