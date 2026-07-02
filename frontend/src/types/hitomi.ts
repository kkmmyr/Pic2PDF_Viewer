/**
 * hitomi.la 新着監視機能の型定義。
 * 詳細は docs/design/詳細設計/機能別/hitomi新着監視設計書.md §4 を参照。
 */

export type RunStatus = 'ok' | 'partial' | 'error' | 'never';

export interface RunStats {
    added: number;
    skipped: number;
    errors: number;
}

export interface RunNowResponse {
    exit_code: number;
    last_run_at: string | null;
    last_run_status: RunStatus;
    last_error: string | null;
    last_run_stats: RunStats | null;
}

export interface ArrivalItem {
    id: number;
    artist: string;
    display_artist: string;
    title: string;
    language: string;
    type: string;
    page_count: number;
    published_at: string;
    discovered_at: string;
    url: string;
    dismissed: boolean;
}

export interface NewArrivalsResponse {
    items: ArrivalItem[];
    last_run_at: string | null;
    last_run_status: RunStatus;
    last_error: string | null;
}

export interface WatchlistEntry {
    display_name: string;
    normalized: string;
    language: string;
    added_at: string;
}

export interface WatchlistResponse {
    artists: WatchlistEntry[];
}
