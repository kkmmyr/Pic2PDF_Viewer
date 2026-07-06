/**
 * 小説テキスト検索・RAG 機能の共通型定義。
 * バックエンド API スキーマと一致させる（docs/design/詳細設計/API.md、一覧は /openapi.json）。
 */

import type { components } from '@/types/api';

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
    ocr_done_at: string | null;
    volume: number | null;
    publisher: string | null;
    asin: string | null;
    series_index: number | null;
}

export interface BookDetail extends BookSummary {
    isbn: string | null;
    summary: string | null;
    summary_generated_at: string | null;
    character_count: number;
    discussion_count: number;
}

export type SimilarBook = components['schemas']['SimilarBookOut'];

// ---------------------------------------------------------------------------
// 書籍メタ編集（4.3）
// ---------------------------------------------------------------------------

export interface NovelMetaPatch {
    authors?: string[];
    series_id?: string;
    volume?: number | null;
    volume_clear?: boolean;
    publisher?: string;
    asin?: string;
    isbn?: string;
    release_date?: string;
}

export type SeriesSummary = components['schemas']['SeriesSummaryOut'];

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
export type RebuildJobMode = 'rebuild' | 'ocr' | 'pdf_text' | 'reocr' | 'full_build';

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

export type RebuildEnqueueResponse = components['schemas']['RebuildEnqueueResponse'];

// ---------------------------------------------------------------------------
// マルチターン会話 QA（B-16）
// ---------------------------------------------------------------------------

export interface ChatSessionSummary {
    id: number;
    scope_type: ScopeType;
    scope_id: string | null;
    title: string | null;
    started_at: string;
    last_message_at: string | null;
    message_count: number;
}

export interface ChatMessage {
    id: number;
    role: 'user' | 'assistant' | 'system';
    content: string;
    eval_count: number | null;
    done_reason: string | null;
    created_at: string;
}

export interface ChatSessionDetail extends ChatSessionSummary {
    messages: ChatMessage[];
}

// ---------------------------------------------------------------------------
// キャラクター辞典（B-15）
// ---------------------------------------------------------------------------

export type CharacterSummary = components['schemas']['CharacterSummary'];
export type CharacterScene = components['schemas']['CharacterScene'];
export type CharacterDetail = components['schemas']['CharacterDetail'];

// ---------------------------------------------------------------------------
// 読書会 番組台本（B-20 / B-28）
// ---------------------------------------------------------------------------

/** 機械チェック 1 項目の結果（B-28）。 */
export interface DiscussionCheckResult {
    id: string;
    label: string;
    passed: boolean;
    detail: string;
}

/** 台本生成後の機械チェック結果一式（B-28）。 */
export interface DiscussionChecks {
    passed: boolean;
    results: DiscussionCheckResult[];
}

/** 台本セグメント（OPフック / テーマ 1 等）の見出し情報（B-28）。 */
export interface DiscussionSegment {
    id: string;
    title: string;
}

export interface DiscussionTurn {
    speaker: string;
    text: string;
    /** v2（番組台本形式）のみ。所属セグメント id。 */
    segment?: string;
}

export interface DiscussionHistoryItem {
    filename: string;
    created_at: string | null;
    personas: { name: string; style_description: string }[];
    turn_count: number;
    turns: DiscussionTurn[];
    /** 1 = 旧ディスカッション形式 / 2 = 番組台本形式（B-28）。 */
    format_version: 1 | 2;
    segments?: DiscussionSegment[] | null;
    checks?: DiscussionChecks | null;
}
