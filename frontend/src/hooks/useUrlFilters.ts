import { useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';

/**
 * author / tag / series フィルターの URL クエリ同期。
 *
 * ドリルダウン後にブラウザの戻るボタンで元の一覧に戻れるようにするため、
 * これら 3 つは URL クエリで保持する（`searchText` は履歴汚染を避けるため別管理）。
 */
export function useUrlFilters() {
    const [searchParams, setSearchParams] = useSearchParams();
    const authorFilter = searchParams.get('author') ?? '';
    const tagFilter = searchParams.get('tag') ?? '';
    const seriesFilter = searchParams.get('series') ?? '';

    const updateUrlFilter = useCallback((key: 'author' | 'tag' | 'series', value: string) => {
        const next = new URLSearchParams(searchParams);
        if (value) next.set(key, value);
        else next.delete(key);
        setSearchParams(next);
    }, [searchParams, setSearchParams]);

    const setAuthorFilter = useCallback((v: string) => updateUrlFilter('author', v), [updateUrlFilter]);
    const setTagFilter = useCallback((v: string) => updateUrlFilter('tag', v), [updateUrlFilter]);
    const setSeriesFilter = useCallback((v: string) => updateUrlFilter('series', v), [updateUrlFilter]);

    /** ライブラリ階層に戻る（author / series を一括クリア。tag は残す） */
    const clearAllDrilldown = useCallback(() => {
        const next = new URLSearchParams(searchParams);
        next.delete('author');
        next.delete('series');
        setSearchParams(next);
    }, [searchParams, setSearchParams]);

    return {
        authorFilter, tagFilter, seriesFilter,
        setAuthorFilter, setTagFilter, setSeriesFilter,
        clearAllDrilldown,
    };
}
