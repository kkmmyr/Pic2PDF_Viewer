import { useCallback } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import type { LibrarySource } from '../../types';
import { API_ENDPOINTS } from '../../config/api';
import apiClient from '../../config/api_client';

export const genresQueryKey = (source: LibrarySource) => ['genres', source] as const;

export function useGenres(source: LibrarySource) {
    const queryClient = useQueryClient();

    const { data: genres = [] } = useQuery<string[]>({
        queryKey: genresQueryKey(source),
        queryFn: async () => {
            try {
                const data = await apiClient.get<unknown, string[]>(API_ENDPOINTS.GENRES, {
                    params: { source },
                });
                return data ?? [];
            } catch {
                return [];
            }
        },
        staleTime: Infinity,
    });

    const addGenre = useCallback(
        async (name: string): Promise<void> => {
            const data = await apiClient.post<unknown, { genres: string[] }>(API_ENDPOINTS.GENRES, {
                source,
                name,
            });
            queryClient.setQueryData<string[]>(genresQueryKey(source), data.genres);
        },
        [source, queryClient],
    );

    const removeGenre = useCallback(
        async (name: string): Promise<void> => {
            const data = await apiClient.delete<unknown, { genres: string[] }>(
                `${API_ENDPOINTS.GENRES}/${encodeURIComponent(name)}`,
                { params: { source } },
            );
            queryClient.setQueryData<string[]>(genresQueryKey(source), data.genres);
        },
        [source, queryClient],
    );

    const reorderGenres = useCallback(
        async (newOrder: string[]): Promise<void> => {
            const prev = genres;
            queryClient.setQueryData<string[]>(genresQueryKey(source), newOrder);
            try {
                await apiClient.patch(API_ENDPOINTS.GENRES_REORDER, { source, genres: newOrder });
            } catch {
                queryClient.setQueryData<string[]>(genresQueryKey(source), prev);
            }
        },
        [source, genres, queryClient],
    );

    return { genres, addGenre, removeGenre, reorderGenres };
}
