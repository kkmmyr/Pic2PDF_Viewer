import { useState, useCallback, useEffect } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import type { ReadState, SortOrder } from '@/types';
import type { LibrarySource } from '@/types';
import type { GroupMode } from './useLibraryGrouping';
import { STORAGE_KEYS } from '@/constants';
import { getStorageJson, setStorageJson } from '@/utils/storage';
import { API_ENDPOINTS } from '@/config/api';
import apiClient from '@/config/api_client';

const SORT_STORAGE_KEY = STORAGE_KEYS.LIBRARY_SORT;
const GROUP_MODE_KEY = 'library_group_mode';
const SHOW_HIDDEN_KEY = 'library_show_hidden';
// 移行元 localStorage キー（DB 移行後は読み出しのみ）
const READ_STATE_FILTER_KEY = 'library_read_state_filter';
const LEGACY_SHOW_UNREAD_ONLY_KEY = 'library_show_unread_only';
const GENRE_FILTER_KEY = 'library_genre_filter';

export type ReadStateFilter = '' | ReadState;

interface PrefsResponse {
    read_state_filter: ReadStateFilter;
    genre_filter: string;
    series_pins: Record<string, string>;
    author_pins: Record<string, string>;
}

/**
 * 旧 library_show_unread_only=true を localStorage の read_state_filter に移行する（移行専用）。
 */
function getLegacyReadStateFilter(): ReadStateFilter {
    const legacy = getStorageJson<boolean | null>(LEGACY_SHOW_UNREAD_ONLY_KEY, null);
    if (legacy === null) return getStorageJson<ReadStateFilter>(READ_STATE_FILTER_KEY, '');
    const migrated: ReadStateFilter = legacy ? 'unread' : '';
    setStorageJson(READ_STATE_FILTER_KEY, migrated);
    try {
        window.localStorage.removeItem(LEGACY_SHOW_UNREAD_ONLY_KEY);
    } catch {
        // localStorage が利用不可（プライベートモード等）なら何もしない
    }
    return migrated;
}

/**
 * ライブラリ表示設定を管理するフック。
 *
 * - sort / groupMode / showHidden: localStorage 永続化（デバイスローカル設定）
 * - readStateFilter / genreFilter: API（meta.db）永続化（デバイス間共有）
 *   初回ロード時に localStorage の既存値を DB に移行して localStorage を削除する。
 */
export function useLibrarySettings(source: LibrarySource) {
    const queryClient = useQueryClient();

    // ── localStorage 管理の設定 ──
    const [sortOrder, setSortOrderState] = useState<SortOrder>(() =>
        getStorageJson<SortOrder>(SORT_STORAGE_KEY, 'name_asc'),
    );
    const [groupMode, setGroupModeState] = useState<GroupMode>(() =>
        getStorageJson<GroupMode>(GROUP_MODE_KEY, 'none'),
    );
    const [showHidden, setShowHiddenState] = useState<boolean>(() =>
        getStorageJson<boolean>(SHOW_HIDDEN_KEY, false),
    );

    const setSortOrder = useCallback((order: SortOrder) => {
        setSortOrderState(order);
        setStorageJson(SORT_STORAGE_KEY, order);
    }, []);

    const setGroupMode = useCallback((mode: GroupMode) => {
        setGroupModeState(mode);
        setStorageJson(GROUP_MODE_KEY, mode);
    }, []);

    const toggleShowHidden = useCallback(() => {
        setShowHiddenState((prev) => {
            const next = !prev;
            setStorageJson(SHOW_HIDDEN_KEY, next);
            return next;
        });
    }, []);

    // ── API 管理の設定（readStateFilter / genreFilter）──
    const { data: prefs } = useQuery<PrefsResponse>({
        queryKey: ['prefs', source],
        queryFn: () => apiClient.get<unknown, PrefsResponse>(API_ENDPOINTS.PREFS(source)),
        staleTime: Infinity,
    });

    const readStateFilter: ReadStateFilter = prefs?.read_state_filter ?? '';
    const genreFilter: string = prefs?.genre_filter ?? '';

    // localStorage → DB の一回限り移行
    useEffect(() => {
        const localRsf = getLegacyReadStateFilter();
        const localGf = getStorageJson<string>(GENRE_FILTER_KEY, '');
        if (localRsf === '' && localGf === '') return;
        // DB にまだ値がない（デフォルト）場合のみ移行
        if (prefs && prefs.read_state_filter === '' && prefs.genre_filter === '') {
            apiClient
                .patch(API_ENDPOINTS.PREFS_FILTERS, {
                    source,
                    read_state_filter: localRsf || null,
                    genre_filter: localGf || null,
                })
                .then(() => {
                    queryClient.invalidateQueries({ queryKey: ['prefs', source] });
                })
                .catch(() => {
                    /* 移行失敗は無視 */
                });
        }
        // 移行元 localStorage を削除
        try {
            window.localStorage.removeItem(READ_STATE_FILTER_KEY);
            window.localStorage.removeItem(GENRE_FILTER_KEY);
        } catch {
            // 無視
        }
        // prefs が取得された後に一度だけ実行
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [prefs !== undefined, source]);

    const setReadStateFilter = useCallback(
        (value: ReadStateFilter) => {
            queryClient.setQueryData<PrefsResponse>(['prefs', source], (old) => ({
                ...(old ?? { genre_filter: '', series_pins: {}, author_pins: {} }),
                read_state_filter: value,
            }));
            apiClient
                .patch(API_ENDPOINTS.PREFS_FILTERS, {
                    source,
                    read_state_filter: value,
                })
                .catch(() => {
                    queryClient.invalidateQueries({ queryKey: ['prefs', source] });
                });
        },
        [source, queryClient],
    );

    const setGenreFilter = useCallback(
        (genre: string) => {
            queryClient.setQueryData<PrefsResponse>(['prefs', source], (old) => ({
                ...(old ?? { read_state_filter: '', series_pins: {}, author_pins: {} }),
                genre_filter: genre,
            }));
            apiClient
                .patch(API_ENDPOINTS.PREFS_FILTERS, {
                    source,
                    genre_filter: genre,
                })
                .catch(() => {
                    queryClient.invalidateQueries({ queryKey: ['prefs', source] });
                });
        },
        [source, queryClient],
    );

    return {
        sortOrder,
        setSortOrder,
        groupMode,
        setGroupMode,
        showHidden,
        toggleShowHidden,
        readStateFilter,
        setReadStateFilter,
        genreFilter,
        setGenreFilter,
    };
}
