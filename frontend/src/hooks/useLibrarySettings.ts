import { useState, useCallback } from 'react';
import type { SortOrder } from '../types';
import type { GroupMode } from './useLibraryGrouping';
import { STORAGE_KEYS } from '../constants';
import { getStorageJson, setStorageJson } from '../utils/storage';

const SORT_STORAGE_KEY = STORAGE_KEYS.LIBRARY_SORT;
const GROUP_MODE_KEY = 'library_group_mode';
const SHOW_HIDDEN_KEY = 'library_show_hidden';
const SHOW_UNREAD_ONLY_KEY = 'library_show_unread_only';
const GENRE_FILTER_KEY = 'library_genre_filter';

/**
 * ライブラリ表示設定（sort / groupMode / showHidden / showUnreadOnly）を localStorage に永続化する。
 * setter は state 更新と localStorage 書き込みをまとめて行う。
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
    const [showUnreadOnly, setShowUnreadOnlyState] = useState<boolean>(() =>
        getStorageJson<boolean>(SHOW_UNREAD_ONLY_KEY, false),
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

    const toggleShowUnreadOnly = useCallback(() => {
        setShowUnreadOnlyState((prev) => {
            const next = !prev;
            setStorageJson(SHOW_UNREAD_ONLY_KEY, next);
            return next;
        });
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
        showUnreadOnly,
        toggleShowUnreadOnly,
        genreFilter,
        setGenreFilter,
    };
}
