import { useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { BookMetaMap, ReadState } from '@/types';
import { API_ENDPOINTS } from '@/config/api';
import apiClient from '@/config/api_client';

export const metaQueryKey = (source: string) => ['meta', source] as const;
const EMPTY_META: BookMetaMap = {};

export function makeBookMetaKey(path: string, name: string): string {
    return path ? `${path}/${name}` : name;
}

export function useBookMetaCore(source: string) {
    const query = useQuery<BookMetaMap>({
        queryKey: metaQueryKey(source),
        queryFn: async () => {
            const data = await apiClient.get<unknown, BookMetaMap>(API_ENDPOINTS.META, {
                params: { source },
            });
            return data ?? {};
        },
        staleTime: Infinity,
    });
    const meta = query.data ?? EMPTY_META;

    const getAuthors = useCallback(
        (path: string, name: string): string[] => {
            return meta[makeBookMetaKey(path, name)]?.authors ?? [];
        },
        [meta],
    );

    const getSeries = useCallback(
        (path: string, name: string): { id: string; title: string; index: number } | null => {
            const e = meta[makeBookMetaKey(path, name)];
            if (!e?.series_id) return null;
            return {
                id: e.series_id,
                title: e.series_title ?? '',
                index: e.series_index ?? 0,
            };
        },
        [meta],
    );

    const isHidden = useCallback(
        (path: string, name: string): boolean => {
            return meta[makeBookMetaKey(path, name)]?.hidden === true;
        },
        [meta],
    );

    const getViewCount = useCallback(
        (path: string, name: string): number => {
            return meta[makeBookMetaKey(path, name)]?.view_count ?? 0;
        },
        [meta],
    );

    const getLastViewedAt = useCallback(
        (path: string, name: string): number | undefined => {
            return meta[makeBookMetaKey(path, name)]?.last_viewed_at;
        },
        [meta],
    );

    const getReadState = useCallback(
        (path: string, name: string): ReadState => {
            const entry = meta[makeBookMetaKey(path, name)];
            if (entry?.read_state) return entry.read_state;
            return (entry?.view_count ?? 0) > 0 ? 'reading' : 'unread';
        },
        [meta],
    );

    return {
        meta,
        fetchMeta: query.refetch,
        isError: query.isError,
        error: query.error,
        getAuthors,
        getSeries,
        isHidden,
        getViewCount,
        getLastViewedAt,
        getReadState,
    };
}
