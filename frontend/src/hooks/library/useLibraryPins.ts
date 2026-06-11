import { useEffect } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import type { LibrarySource } from '@/types';
import { STORAGE_KEYS } from '@/constants';
import { getStorageJson } from '@/utils/storage';
import { API_ENDPOINTS } from '@/config/api';
import apiClient from '@/config/api_client';

/** groupId → ピン留めされた book_name。1グループにつき1冊のみ */
export type PinsMap = Record<string, string>;

interface PrefsResponse {
    read_state_filter: string;
    genre_filter: string;
    series_pins: PinsMap;
    author_pins: PinsMap;
}

/**
 * シリーズ/作者集約カードの代表ピン管理（§12）。
 *
 * - seriesPins / authorPins は meta.db に永続化（デバイス間共有）
 * - 同じ source の useLibrarySettings と React Query キャッシュ ['prefs', source] を共有する
 * - 初回ロード時に localStorage の既存データを DB へ移行して localStorage を削除する
 */
export function useLibraryPins(source: LibrarySource) {
    const queryClient = useQueryClient();

    const { data: prefs } = useQuery<PrefsResponse>({
        queryKey: ['prefs', source],
        queryFn: () => apiClient.get<unknown, PrefsResponse>(API_ENDPOINTS.PREFS(source)),
        staleTime: Infinity,
    });

    const seriesPins: PinsMap = prefs?.series_pins ?? {};
    const authorPins: PinsMap = prefs?.author_pins ?? {};

    // localStorage → DB の一回限り移行
    useEffect(() => {
        if (!prefs) return;
        const seriesKey = `${STORAGE_KEYS.SERIES_PINS_PREFIX}${source}`;
        const authorKey = `${STORAGE_KEYS.AUTHOR_PINS_PREFIX}${source}`;
        const localSeries = getStorageJson<PinsMap>(seriesKey, {});
        const localAuthor = getStorageJson<PinsMap>(authorKey, {});
        const hasLocal = Object.keys(localSeries).length > 0 || Object.keys(localAuthor).length > 0;
        if (!hasLocal) return;
        // DB がまだ空の場合のみ移行
        const dbEmpty =
            Object.keys(prefs.series_pins).length === 0 &&
            Object.keys(prefs.author_pins).length === 0;
        if (dbEmpty) {
            const migrations: Promise<unknown>[] = [];
            for (const [groupId, bookName] of Object.entries(localSeries)) {
                migrations.push(
                    apiClient.put(API_ENDPOINTS.PREFS_PINS, {
                        source,
                        pin_type: 'series',
                        group_id: groupId,
                        book_name: bookName,
                    }),
                );
            }
            for (const [groupId, bookName] of Object.entries(localAuthor)) {
                migrations.push(
                    apiClient.put(API_ENDPOINTS.PREFS_PINS, {
                        source,
                        pin_type: 'author',
                        group_id: groupId,
                        book_name: bookName,
                    }),
                );
            }
            Promise.all(migrations)
                .then(() => {
                    queryClient.invalidateQueries({ queryKey: ['prefs', source] });
                })
                .catch(() => {
                    /* 移行失敗は無視 */
                });
        }
        // 移行元 localStorage を削除
        try {
            window.localStorage.removeItem(seriesKey);
            window.localStorage.removeItem(authorKey);
        } catch {
            // 無視
        }
        // prefs 取得後に一度だけ実行
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [prefs !== undefined, source]);

    const toggleSeriesPin = (seriesId: string, bookName: string) => {
        const isAlreadyPinned = prefs?.series_pins[seriesId] === bookName;
        // 楽観的更新
        queryClient.setQueryData<PrefsResponse>(['prefs', source], (old) => {
            if (!old) return old;
            const next = { ...old.series_pins };
            if (isAlreadyPinned) {
                delete next[seriesId];
            } else {
                next[seriesId] = bookName;
            }
            return { ...old, series_pins: next };
        });
        if (isAlreadyPinned) {
            apiClient
                .delete(
                    `${API_ENDPOINTS.PREFS_PINS}?source=${encodeURIComponent(source)}&pin_type=series&group_id=${encodeURIComponent(seriesId)}`,
                )
                .catch(() => queryClient.invalidateQueries({ queryKey: ['prefs', source] }));
        } else {
            apiClient
                .put(API_ENDPOINTS.PREFS_PINS, {
                    source,
                    pin_type: 'series',
                    group_id: seriesId,
                    book_name: bookName,
                })
                .catch(() => queryClient.invalidateQueries({ queryKey: ['prefs', source] }));
        }
    };

    const toggleAuthorPin = (authorGroupId: string, bookName: string) => {
        const isAlreadyPinned = prefs?.author_pins[authorGroupId] === bookName;
        // 楽観的更新
        queryClient.setQueryData<PrefsResponse>(['prefs', source], (old) => {
            if (!old) return old;
            const next = { ...old.author_pins };
            if (isAlreadyPinned) {
                delete next[authorGroupId];
            } else {
                next[authorGroupId] = bookName;
            }
            return { ...old, author_pins: next };
        });
        if (isAlreadyPinned) {
            apiClient
                .delete(
                    `${API_ENDPOINTS.PREFS_PINS}?source=${encodeURIComponent(source)}&pin_type=author&group_id=${encodeURIComponent(authorGroupId)}`,
                )
                .catch(() => queryClient.invalidateQueries({ queryKey: ['prefs', source] }));
        } else {
            apiClient
                .put(API_ENDPOINTS.PREFS_PINS, {
                    source,
                    pin_type: 'author',
                    group_id: authorGroupId,
                    book_name: bookName,
                })
                .catch(() => queryClient.invalidateQueries({ queryKey: ['prefs', source] }));
        }
    };

    return { seriesPins, authorPins, toggleSeriesPin, toggleAuthorPin };
}
