import { useState, useCallback, useEffect } from 'react';
import type { LibrarySource } from '../types';
import { STORAGE_KEYS } from '../constants';

const storageKey = (source: LibrarySource) => `${STORAGE_KEYS.FAVORITES_PREFIX}${source}`;

/**
 * お気に入り管理フック。
 * - ソース (generated / kindle / novel) 別に localStorage に保存
 * - マウント時に localStorage から復元
 */
export function useFavorites(source: LibrarySource) {
    const [favorites, setFavorites] = useState<Set<string>>(() => {
        try {
            const raw = localStorage.getItem(storageKey(source));
            return raw ? new Set<string>(JSON.parse(raw)) : new Set<string>();
        } catch {
            return new Set<string>();
        }
    });

    // ソースが切り替わったら該当ソースのお気に入りを読み直す
    useEffect(() => {
        try {
            const raw = localStorage.getItem(storageKey(source));
            setFavorites(raw ? new Set<string>(JSON.parse(raw)) : new Set<string>());
        } catch {
            setFavorites(new Set<string>());
        }
    }, [source]);

    const persist = useCallback((next: Set<string>) => {
        localStorage.setItem(storageKey(source), JSON.stringify([...next]));
    }, [source]);

    const toggle = useCallback((name: string) => {
        setFavorites(prev => {
            const next = new Set(prev);
            if (next.has(name)) {
                next.delete(name);
            } else {
                next.add(name);
            }
            persist(next);
            return next;
        });
    }, [persist]);

    const isFavorite = useCallback((name: string) => favorites.has(name), [favorites]);

    return { favorites, toggle, isFavorite };
}
