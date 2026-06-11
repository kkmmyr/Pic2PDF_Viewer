/**
 * C-12: キャラクタ関係グラフ API クライアント。
 */
import apiClient from '@/config/api_client';

const PREFIX = '/api/novel_graph';

export interface GraphNode {
    id: number;
    label: string;
    book_id: number;
}

export interface GraphEdge {
    id: number;
    from: number;
    to: number;
    label: string;
    weight: number;
}

export interface GraphData {
    nodes: GraphNode[];
    edges: GraphEdge[];
}

export interface BookEntry {
    id: number;
    name: string;
}

export function fetchSeriesList(): Promise<string[]> {
    return apiClient.get<unknown, string[]>(`${PREFIX}/series`);
}

export function fetchBooksInSeries(seriesId: string): Promise<BookEntry[]> {
    return apiClient.get<unknown, BookEntry[]>(
        `${PREFIX}/series/${encodeURIComponent(seriesId)}/books`,
    );
}

export function fetchGraph(seriesId: string, bookIds?: number[]): Promise<GraphData> {
    const params = bookIds && bookIds.length > 0 ? { book_ids: bookIds.join(',') } : undefined;
    return apiClient.get<unknown, GraphData>(
        `${PREFIX}/series/${encodeURIComponent(seriesId)}/graph`,
        { params },
    );
}
