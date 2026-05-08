import { useState, useEffect, useCallback } from 'react';
import type { BookMetaMap, ReadState } from '../types';
import { API_ENDPOINTS } from '../config/api';
import apiClient from '../config/api_client';

/**
 * 書籍メタデータの取得・読み取り基盤フック。
 *
 * `meta` 状態と `setMeta` を保持し、各種 getter を提供する。書き込み系は
 * `useBookMetaWrite` / `useBookSeries` / `useBookView` が `setMeta` / `makeKey` を
 * 受け取って実装し、`useBookMeta` がこれらを合成する。
 */
export function useBookMetaCore(source: string) {
    const [meta, setMeta] = useState<BookMetaMap>({});

    const fetchMeta = useCallback(async () => {
        try {
            const data = await apiClient.get<unknown, BookMetaMap>(API_ENDPOINTS.META, {
                params: { source },
            });
            setMeta(data ?? {});
        } catch {
            setMeta({});
        }
    }, [source]);

    useEffect(() => {
        fetchMeta();
    }, [fetchMeta]);

    const makeKey = useCallback((path: string, name: string) => {
        return path ? `${path}/${name}` : name;
    }, []);

    const getAuthors = useCallback(
        (path: string, name: string): string[] => {
            return meta[makeKey(path, name)]?.authors ?? [];
        },
        [meta, makeKey],
    );

    const getTags = useCallback(
        (path: string, name: string): string[] => {
            return meta[makeKey(path, name)]?.tags ?? [];
        },
        [meta, makeKey],
    );

    const getSeries = useCallback(
        (path: string, name: string): { id: string; title: string; index: number } | null => {
            const e = meta[makeKey(path, name)];
            if (!e?.series_id) return null;
            return {
                id: e.series_id,
                title: e.series_title ?? '',
                index: e.series_index ?? 0,
            };
        },
        [meta, makeKey],
    );

    const isHidden = useCallback(
        (path: string, name: string): boolean => {
            return meta[makeKey(path, name)]?.hidden === true;
        },
        [meta, makeKey],
    );

    const getViewCount = useCallback(
        (path: string, name: string): number => {
            return meta[makeKey(path, name)]?.view_count ?? 0;
        },
        [meta, makeKey],
    );

    const getLastViewedAt = useCallback(
        (path: string, name: string): number | undefined => {
            return meta[makeKey(path, name)]?.last_viewed_at;
        },
        [meta, makeKey],
    );

    const getReadState = useCallback(
        (path: string, name: string): ReadState => {
            const entry = meta[makeKey(path, name)];
            // 明示フィールドを優先、無ければ view_count から派生（後方互換）
            if (entry?.read_state) return entry.read_state;
            return (entry?.view_count ?? 0) > 0 ? 'reading' : 'unread';
        },
        [meta, makeKey],
    );

    return {
        meta,
        setMeta,
        makeKey,
        fetchMeta,
        getAuthors,
        getTags,
        getSeries,
        isHidden,
        getViewCount,
        getLastViewedAt,
        getReadState,
    };
}

export type SetBookMeta = ReturnType<typeof useBookMetaCore>['setMeta'];
export type MakeBookMetaKey = ReturnType<typeof useBookMetaCore>['makeKey'];
