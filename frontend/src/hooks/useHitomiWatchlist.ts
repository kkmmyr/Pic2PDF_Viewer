import { useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '@/config/api_client';
import { API_ENDPOINTS } from '@/config/api';
import { errorMessage } from '@/utils/error';
import type { WatchlistEntry, WatchlistResponse } from '@/types/hitomi';

const WATCHLIST_QUERY_KEY = ['hitomiWatchlist'] as const;

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
    const queryClient = useQueryClient();

    const query = useQuery({
        queryKey: WATCHLIST_QUERY_KEY,
        queryFn: async () => {
            const resp = await apiClient.get<unknown, WatchlistResponse>(
                API_ENDPOINTS.HITOMI_WATCHLIST,
            );
            return resp.artists;
        },
        staleTime: Infinity,
    });

    const addMutation = useMutation({
        mutationFn: ({ displayName, language }: { displayName: string; language: string }) =>
            apiClient.post<unknown, { message: string; normalized: string }>(
                API_ENDPOINTS.HITOMI_WATCHLIST,
                { display_name: displayName, language },
            ),
        onSuccess: () => queryClient.invalidateQueries({ queryKey: WATCHLIST_QUERY_KEY }),
    });

    const removeMutation = useMutation({
        mutationFn: ({ normalized, language }: { normalized: string; language: string }) =>
            apiClient.delete(API_ENDPOINTS.HITOMI_WATCHLIST_DELETE(normalized, language)),
        onMutate: ({ normalized, language }) => {
            const prev = queryClient.getQueryData<WatchlistEntry[]>(WATCHLIST_QUERY_KEY);
            queryClient.setQueryData<WatchlistEntry[]>(WATCHLIST_QUERY_KEY, (old) =>
                old?.filter((e) => !(e.normalized === normalized && e.language === language)),
            );
            return { prev };
        },
        onError: (_err, _vars, context) => {
            if (context?.prev !== undefined) {
                queryClient.setQueryData(WATCHLIST_QUERY_KEY, context.prev);
            }
        },
    });

    const addArtist = useCallback(
        async (displayName: string, language: string): Promise<WatchlistEntry> => {
            const resp = await addMutation.mutateAsync({ displayName, language });
            return {
                display_name: displayName.trim(),
                normalized: resp.normalized,
                language,
                added_at: new Date().toISOString().slice(0, 10),
            };
        },
        [addMutation],
    );

    const removeArtist = useCallback(
        async (normalized: string, language: string): Promise<void> => {
            await removeMutation.mutateAsync({ normalized, language });
        },
        [removeMutation],
    );

    const refresh = useCallback(async () => {
        await queryClient.refetchQueries({ queryKey: WATCHLIST_QUERY_KEY });
    }, [queryClient]);

    return {
        artists: query.data ?? [],
        loading: query.isLoading,
        error: query.error instanceof Error ? errorMessage(query.error, '不明なエラー') : null,
        refresh,
        addArtist,
        removeArtist,
    };
}
