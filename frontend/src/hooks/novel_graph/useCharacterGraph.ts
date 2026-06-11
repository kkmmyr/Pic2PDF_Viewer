/**
 * C-12: キャラクタ関係グラフのデータ取得フック。
 */
import { useState, useEffect, useCallback } from 'react';
import {
    fetchSeriesList,
    fetchBooksInSeries,
    fetchGraph,
    type BookEntry,
    type GraphData,
} from '@/features/novel_graph/api';

export function useCharacterGraph() {
    const [seriesList, setSeriesList] = useState<string[]>([]);
    const [selectedSeries, setSelectedSeries] = useState<string | null>(null);
    const [books, setBooks] = useState<BookEntry[]>([]);
    const [selectedBookIds, setSelectedBookIds] = useState<number[]>([]);
    const [graphData, setGraphData] = useState<GraphData | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // シリーズ一覧を初期ロード
    useEffect(() => {
        fetchSeriesList()
            .then(setSeriesList)
            .catch(() => setError('シリーズ一覧の取得に失敗しました'));
    }, []);

    // シリーズ選択時に書籍一覧を取得
    useEffect(() => {
        if (!selectedSeries) {
            setBooks([]);
            setSelectedBookIds([]);
            setGraphData(null);
            return;
        }
        fetchBooksInSeries(selectedSeries)
            .then((bs) => {
                setBooks(bs);
                setSelectedBookIds(bs.map((b) => b.id));
            })
            .catch(() => setError('書籍一覧の取得に失敗しました'));
    }, [selectedSeries]);

    // 書籍フィルタ変更時にグラフを再取得
    const loadGraph = useCallback(() => {
        if (!selectedSeries) return;
        setLoading(true);
        setError(null);
        fetchGraph(selectedSeries, selectedBookIds.length > 0 ? selectedBookIds : undefined)
            .then(setGraphData)
            .catch(() => setError('グラフデータの取得に失敗しました'))
            .finally(() => setLoading(false));
    }, [selectedSeries, selectedBookIds]);

    useEffect(() => {
        loadGraph();
    }, [loadGraph]);

    const toggleBook = useCallback((bookId: number) => {
        setSelectedBookIds((prev) =>
            prev.includes(bookId) ? prev.filter((id) => id !== bookId) : [...prev, bookId],
        );
    }, []);

    return {
        seriesList,
        selectedSeries,
        setSelectedSeries,
        books,
        selectedBookIds,
        toggleBook,
        graphData,
        loading,
        error,
    };
}
