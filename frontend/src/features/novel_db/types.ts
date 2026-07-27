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

type GeneratedRebuildRequest = components['schemas']['RebuildRequest'];
export type RebuildJobType = GeneratedRebuildRequest['type'];
export type RebuildJobMode = GeneratedRebuildRequest['mode'];
export type RebuildJob =
    | components['schemas']['RebuildRunningJobOut']
    | components['schemas']['RebuildQueuedJobOut']
    | components['schemas']['RebuildFinishedJobOut'];
export type RebuildStatus = components['schemas']['RebuildStatusResponse'];

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

export type DiscussionCheckResult = components['schemas']['DiscussionCheckResultOut'];
export type DiscussionChecks = components['schemas']['DiscussionChecksOut'];
export type DiscussionSegment = components['schemas']['DiscussionSegmentOut'];
export type DiscussionTurn = components['schemas']['DiscussionTurnOut'];
export type DiscussionHistoryItem = components['schemas']['DiscussionHistoryItemOut'];
