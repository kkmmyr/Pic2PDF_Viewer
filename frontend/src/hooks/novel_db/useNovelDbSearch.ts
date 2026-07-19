import { useEffect, useState } from 'react';
import { useInfiniteQuery } from '@tanstack/react-query';

import { NOVEL_DB_CONFIG } from '@/constants';
import { searchHits } from '@/features/novel_db/api';
import { novelDbKeys } from '@/features/novel_db/queries';
import type { Scope, SearchHit } from '@/features/novel_db/types';

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

    useEffect(() => {
        const timer = setTimeout(
            () => setDebouncedQuery(query),
            NOVEL_DB_CONFIG.SEARCH_DEBOUNCE_MS,
        );
        return () => clearTimeout(timer);
    }, [query]);

    const trimmedQuery = debouncedQuery.trim();
    const searchQuery = useInfiniteQuery({
        queryKey: novelDbKeys.search(trimmedQuery, scope),
        queryFn: ({ pageParam }) =>
            searchHits({
                query: trimmedQuery,
                scope,
                offset: pageParam,
                limit: NOVEL_DB_CONFIG.SEARCH_PAGE_SIZE,
            }),
        initialPageParam: 0,
        enabled: trimmedQuery.length > 0,
        getNextPageParam: (lastPage) => {
            const nextOffset = lastPage.offset + lastPage.hits.length;
            return nextOffset < lastPage.total ? nextOffset : undefined;
        },
    });

    const hits = searchQuery.data?.pages.flatMap((page) => page.hits) ?? [];
    const total = searchQuery.data?.pages[0]?.total ?? 0;

    return {
        query,
        setQuery,
        hits,
        total,
        hasMore: searchQuery.hasNextPage,
        isSearching: searchQuery.isFetching,
        error: searchQuery.error instanceof Error ? searchQuery.error.message : null,
        loadMore: async () => {
            if (!searchQuery.hasNextPage || searchQuery.isFetchingNextPage) return;
            await searchQuery.fetchNextPage();
        },
    };
}
