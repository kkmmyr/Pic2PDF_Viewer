import { useState, useCallback } from 'react';
import type { ReadState, SortOrder } from '../types';
import type { GroupMode } from './useLibraryGrouping';
import { STORAGE_KEYS } from '../constants';
import { getStorageJson, setStorageJson } from '../utils/storage';

const SORT_STORAGE_KEY = STORAGE_KEYS.LIBRARY_SORT;
const GROUP_MODE_KEY = 'library_group_mode';
const SHOW_HIDDEN_KEY = 'library_show_hidden';
// A-1 で新設。後方互換のため旧 SHOW_UNREAD_ONLY_KEY=true は初回ロード時に 'unread' へ移行する。
const READ_STATE_FILTER_KEY = 'library_read_state_filter';
const LEGACY_SHOW_UNREAD_ONLY_KEY = 'library_show_unread_only';
const GENRE_FILTER_KEY = 'library_genre_filter';

export type ReadStateFilter = '' | ReadState;

/**
 * 旧 library_show_unread_only=true を新 library_read_state_filter='unread' に移行する。
 * 1 回呼ぶと旧キーは削除される（再移行を防ぐ）。
 */
function migrateLegacyUnreadFilter(): ReadStateFilter {
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
 * ライブラリ表示設定（sort / groupMode / showHidden / readStateFilter / genreFilter）を
 * localStorage に永続化する。setter は state 更新と localStorage 書き込みをまとめて行う。
 */
export function useLibrarySettings() {
    const [sortOrder, setSortOrderState] = useState<SortOrder>(() =>
        getStorageJson<SortOrder>(SORT_STORAGE_KEY, 'name_asc'),
    );
    const [groupMode, setGroupModeState] = useState<GroupMode>(() =>
        getStorageJson<GroupMode>(GROUP_MODE_KEY, 'none'),
    );
    const [showHidden, setShowHiddenState] = useState<boolean>(() =>
        getStorageJson<boolean>(SHOW_HIDDEN_KEY, false),
    );
    const [readStateFilter, setReadStateFilterState] = useState<ReadStateFilter>(
        () => migrateLegacyUnreadFilter(),
    );
    const [genreFilter, setGenreFilterState] = useState<string>(() =>
        getStorageJson<string>(GENRE_FILTER_KEY, ''),
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

    const setReadStateFilter = useCallback((value: ReadStateFilter) => {
        setReadStateFilterState(value);
        setStorageJson(READ_STATE_FILTER_KEY, value);
    }, []);

    const setGenreFilter = useCallback((genre: string) => {
        setGenreFilterState(genre);
        setStorageJson(GENRE_FILTER_KEY, genre);
    }, []);

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
