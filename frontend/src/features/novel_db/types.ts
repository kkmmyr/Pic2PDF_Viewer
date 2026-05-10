/**
 * 小説テキスト検索・RAG 機能の共通型定義。
 * バックエンド API スキーマと一致させる（docs/03_詳細設計/API仕様書.md §7）。
 */

export type ScopeType = 'all' | 'series' | 'book';

export interface Scope {
    type: ScopeType;
    /** scope=series のとき series_id、scope=book のとき書籍 stem。scope=all のとき null。 */
    id?: string | null;
}

export interface BookSummary {
    name: string;
    authors: string[];
    series_id: string | null;
    series_title: string | null;
    is_indexed: boolean;
    page_count: number | null;
    indexed_at: string | null;
    thumbnail_url: string | null;
}

export interface SeriesSummary {
    id: string;
    name: string;
    book_count: number;
}

export interface SearchHit {
    book_name: string;
    page_no: number;
    /** バックエンドで `<mark>` のみ許可済み。`dangerouslySetInnerHTML` で安全に描画可能。 */
    snippet: string;
    has_highlight: boolean;
    image_url: string | null;
    rrf_score: number;
}

export interface SearchResponse {
    hits: SearchHit[];
    total: number;
    offset: number;
    limit: number;
}

export interface QaHistoryEntry {
    id: number;
    asked_at: string;
    finished_at: string | null;
    scope: Scope;
    question: string;
    answer_preview: string;
    done_reason: string | null;
}

export interface QaHistoryListResponse {
    items: QaHistoryEntry[];
    total: number;
}

export interface QaHistoryDetail {
    id: number;
    asked_at: string;
    finished_at: string | null;
    scope: Scope;
    question: string;
    answer: string;
    prompt: string;
    context: SearchHit[];
    model: string;
    options: Record<string, unknown>;
    eval_count: number | null;
    done_reason: string | null;
    error_message: string | null;
}

export type RebuildJobType = 'book' | 'series' | 'all';
export type RebuildJobMode = 'pdf_text' | 'reocr';

export interface RebuildJob {
    id: number;
    type: RebuildJobType;
    target_id: string | null;
    mode: RebuildJobMode;
    enqueued_at?: string;
    started_at?: string;
    finished_at?: string;
    progress_total?: number | null;
    progress_done?: number | null;
    state?: string;
    error_message?: string | null;
}

export interface RebuildStatus {
    is_running: boolean;
    current_job: RebuildJob | null;
    queued_jobs: RebuildJob[];
    recent_finished: RebuildJob[];
}

export interface RebuildEnqueueResponse {
    job_id: number;
    queued_position: number;
}
