import { useState, useEffect, useCallback } from 'react';
import type { LibrarySource } from '../types';
import { API_ENDPOINTS } from '../config/api';
import apiClient from '../config/api_client';

export function useGenres(source: LibrarySource) {
    const [genres, setGenres] = useState<string[]>([]);

    const fetchGenres = useCallback(async () => {
        try {
            const data = await apiClient.get<unknown, string[]>(
                API_ENDPOINTS.GENRES,
                { params: { source } }
            );
            setGenres(data ?? []);
        } catch {
            setGenres([]);
        }
    }, [source]);

    useEffect(() => {
        fetchGenres();
    }, [fetchGenres]);

    const addGenre = useCallback(async (name: string): Promise<void> => {
        const data = await apiClient.post<unknown, { genres: string[] }>(
            API_ENDPOINTS.GENRES,
            { source, name }
        );
        setGenres(data.genres);
    }, [source]);

    const removeGenre = useCallback(async (name: string): Promise<void> => {
        const data = await apiClient.delete<unknown, { genres: string[] }>(
            `${API_ENDPOINTS.GENRES}/${encodeURIComponent(name)}`,
            { params: { source } }
        );
        setGenres(data.genres);
    }, [source]);

    const reorderGenres = useCallback(async (newOrder: string[]): Promise<void> => {
        const prev = genres;
        setGenres(newOrder);
        try {
            await apiClient.patch(API_ENDPOINTS.GENRES_REORDER, { source, genres: newOrder });
        } catch {
            setGenres(prev);
        }
    }, [source, genres]);

    return { genres, addGenre, removeGenre, reorderGenres };
}
