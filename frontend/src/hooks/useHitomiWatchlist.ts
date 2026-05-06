import { useCallback, useEffect, useState } from 'react';
import apiClient from '../config/api_client';
import { API_ENDPOINTS } from '../config/api';
import type { WatchlistEntry, WatchlistResponse } from '../types/hitomi';

interface UseHitomiWatchlistResult {
    artists: WatchlistEntry[];
    loading: boolean;
    error: string | null;
    refresh: () => Promise<void>;
    /** 追加に成功すれば WatchlistEntry を返し、失敗時はエラーを throw する */
    addArtist: (displayName: string, language: string) => Promise<WatchlistEntry>;
    /** 削除に成功すれば true、対象が無ければ ApiError 404 が throw される */
    removeArtist: (normalized: string, language: string) => Promise<void>;
}

/**
 * hitomi.la 監視対象 (watchlist) の CRUD を提供するフック。
 * 新着一覧フックとは独立。ダイアログ内で使う想定。
 */
export function useHitomiWatchlist(): UseHitomiWatchlistResult {
    const [artists, setArtists] = useState<WatchlistEntry[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const refresh = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const resp = await apiClient.get<unknown, WatchlistResponse>(
                API_ENDPOINTS.HITOMI_WATCHLIST,
            );
            setArtists(resp.artists);
        } catch (e) {
            setError(e instanceof Error ? e.message : '不明なエラー');
        } finally {
            setLoading(false);
        }
    }, []);

    const addArtist = useCallback(
        async (displayName: string, language: string) => {
            const resp = await apiClient.post<unknown, { message: string; normalized: string }>(
                API_ENDPOINTS.HITOMI_WATCHLIST,
                { display_name: displayName, language },
            );
            // サーバ正規化後の値を含む新エントリを再取得
            await refresh();
            return {
                display_name: displayName.trim(),
                normalized: resp.normalized,
                language,
                added_at: new Date().toISOString().slice(0, 10),
            };
        },
        [refresh],
    );

    const removeArtist = useCallback(
        async (normalized: string, language: string) => {
            // 楽観的更新
            const prev = artists;
            setArtists(
                artists.filter((e) => !(e.normalized === normalized && e.language === language)),
            );
            try {
                await apiClient.delete(API_ENDPOINTS.HITOMI_WATCHLIST_DELETE(normalized, language));
            } catch (e) {
                setArtists(prev);
                throw e;
            }
        },
        [artists],
    );

    useEffect(() => {
        refresh();
    }, [refresh]);

    return { artists, loading, error, refresh, addArtist, removeArtist };
}
