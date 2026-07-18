import { useCallback, useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';

import { fetchBooksInSeries, fetchGraph, fetchSeriesList } from '@/features/novel_graph/api';

export function useCharacterGraph() {
    const [selectedSeries, setSelectedSeries] = useState<string | null>(null);
    const [selectedBookIds, setSelectedBookIds] = useState<number[]>([]);

    const seriesQuery = useQuery({
        queryKey: ['novelGraphSeries'],
        queryFn: fetchSeriesList,
        staleTime: Infinity,
    });
    const booksQuery = useQuery({
        queryKey: ['novelGraphBooks', selectedSeries],
        queryFn: () => fetchBooksInSeries(selectedSeries!),
        enabled: selectedSeries !== null,
    });

    useEffect(() => {
        setSelectedBookIds(booksQuery.data?.map((book) => book.id) ?? []);
    }, [booksQuery.data, selectedSeries]);

    const graphQuery = useQuery({
        queryKey: ['novelCharacterGraph', selectedSeries, selectedBookIds],
        queryFn: () =>
            fetchGraph(selectedSeries!, selectedBookIds.length > 0 ? selectedBookIds : undefined),
        enabled: selectedSeries !== null && booksQuery.isSuccess,
    });

    const toggleBook = useCallback((bookId: number) => {
        setSelectedBookIds((previous) =>
            previous.includes(bookId)
                ? previous.filter((id) => id !== bookId)
                : [...previous, bookId],
        );
    }, []);

    const queryError = seriesQuery.error ?? booksQuery.error ?? graphQuery.error;

    return {
        seriesList: seriesQuery.data ?? [],
        selectedSeries,
        setSelectedSeries,
        books: booksQuery.data ?? [],
        selectedBookIds,
        toggleBook,
        graphData: graphQuery.data ?? null,
        loading: graphQuery.isFetching,
        error: queryError instanceof Error ? queryError.message : null,
    };
}
