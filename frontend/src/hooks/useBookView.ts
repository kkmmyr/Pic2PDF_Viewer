import { useCallback } from 'react';
import { API_ENDPOINTS } from '../config/api';
import apiClient from '../config/api_client';
import type { SetBookMeta, MakeBookMetaKey } from './useBookMetaCore';

/**
 * 書籍の閲覧記録を扱うフック。
 *
 * `recordView` は失敗してもユーザー体験に影響しないため例外は握りつぶす。
 */
export function useBookView(source: string, setMeta: SetBookMeta, makeKey: MakeBookMetaKey) {
    const recordView = useCallback(
        async (path: string, name: string): Promise<void> => {
            try {
                const res = await apiClient.post<
                    unknown,
                    { view_count: number; last_viewed_at: number }
                >(API_ENDPOINTS.META_VIEW, { path, name, source });
                setMeta((prev) => {
                    const key = makeKey(path, name);
                    const existing = prev[key] ?? { authors: [] };
                    return {
                        ...prev,
                        [key]: {
                            ...existing,
                            view_count: res.view_count,
                            last_viewed_at: res.last_viewed_at,
                        },
                    };
                });
            } catch {
                // 閲覧記録の失敗はユーザー体験に影響しないので握りつぶす
            }
        },
        [source, setMeta, makeKey],
    );

    return { recordView };
}
