/**
 * 小説テキスト検索・RAG 機能の共通型定義。
 * バックエンド API スキーマと一致させる（docs/design/詳細設計/API.md、一覧は /openapi.json）。
 */

import type { components } from '@/types/api';

export type Scope = components['schemas']['ScopeModel'];
export type ScopeType = Scope['type'];

export type BookSummary = components['schemas']['BookSummaryOut'];
export type BookDetail = components['schemas']['BookDetailOut'];

export type SimilarBook = components['schemas']['SimilarBookOut'];

// ---------------------------------------------------------------------------
// 書籍メタ編集（4.3）
// ---------------------------------------------------------------------------

type GeneratedNovelMetaPatch = components['schemas']['NovelMetaPatchRequest'];
export type NovelMetaPatch = Omit<GeneratedNovelMetaPatch, 'volume_clear'> & {
    volume_clear?: boolean;
};

export type SeriesSummary = components['schemas']['SeriesSummaryOut'];

export type SearchHit = components['schemas']['SearchHitOut'];
export type SearchResponse = components['schemas']['SearchResponse'];
export type QaHistoryEntry = components['schemas']['QaHistoryItemOut'];
export type QaHistoryListResponse = components['schemas']['QaHistoryResponse'];
export type QaHistoryDetail = components['schemas']['QaHistoryDetailResponse'];

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

export type ChatSessionSummary = components['schemas']['ChatSessionSummary'];
export type ChatMessage = components['schemas']['ChatMessagePayload'];
export type ChatSessionDetail = components['schemas']['ChatSessionDetailPayload'];

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
