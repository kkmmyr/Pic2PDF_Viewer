import type { components } from './api';

/**
 * PDFファイル情報
 * Note: generated PdfFileOut has `thumbnail?: string | null` (optional), but runtime always includes it.
 */
export interface PdfFile {
    name: string;
    thumbnail: string | null;
    created_at: number;
}

/** 書籍画像APIレスポンス */
export type BookImagesResponse = components['schemas']['BookImagesResponse'];

/** ページ削除APIレスポンス */
export type DeletePagesResponse = components['schemas']['DeletePagesResponse'];

/**
 * OCR ステータスAPIレスポンス
 */
export interface OcrStatusResponse {
    status: 'idle' | 'running' | 'error';
    last_return_code: number | null;
    logs: string[];
}

/**
 * 読み取り方向
 */
export type ReadingDirection = 'rtl' | 'ltr';

/**
 * 見開きモード
 * - 'auto'   : ページの縦横比で自動判定（横長→1ページ、縦長→見開き）
 * - 'spread' : 常に見開き（2ページ）表示
 * - 'single' : 常に1ページ表示
 */
export type SpreadMode = 'auto' | 'spread' | 'single';

/**
 * ページ位置
 */
export type PageSide = 'left' | 'right' | 'single';

/**
 * ライブラリソース
 */
export type LibrarySource = 'doujin' | 'comic' | 'novel';

/**
 * Generator ジョブステータス
 */
type GenerateJobStatus = 'pending' | 'running' | 'completed' | 'failed';

export interface GenerateFailedItem {
    name: string;
    error: string;
}

export interface GenerateJob {
    job_id: string;
    status: GenerateJobStatus;
    /** 現在処理中のアイテム名 */
    current_item: string | null;
    /** 生成済みファイル一覧（完了後に設定） */
    files: string[];
    /** 失敗した書籍とエラー内容（完了後に設定）。サイレント失敗の可視化用 */
    failed_items: GenerateFailedItem[];
    message: string;
    error: string | null;
}

// OpenAPIのstateはstring、nullable項目はoptionalで生成されるため、
// UIで必要な閉じたunionと必須keyをこのadapter型で狭める。
export type DoujinWatcherState =
    | 'idle'
    | 'waiting_stable'
    | 'running'
    | 'input_missing'
    | 'disabled';

export interface DoujinWatcherPendingItem {
    name: string;
    kind: 'zip' | 'folder';
}

export interface DoujinWatcherLastAutoJob {
    job_id: string;
    status: string;
    finished_at: string;
}

export interface DoujinWatcherStatus {
    enabled: boolean;
    state: DoujinWatcherState;
    interval_sec: number;
    last_scan_at: string | null;
    pending_items: DoujinWatcherPendingItem[];
    active_job_id: string | null;
    last_auto_job: DoujinWatcherLastAutoJob | null;
    retry_blocked: boolean;
}

/**
 * 並び替え順序
 */
export type SortOrder =
    | 'name_asc'
    | 'name_desc'
    | 'date_asc'
    | 'date_desc'
    | 'favorites_first'
    | 'view_desc'
    | 'recent_view';

/**
 * 読書状態。
 *
 * - 'unread'  : 未読（NEW バッジ）
 * - 'reading' : 読書中（📖 バッジ）
 * - 'done'    : 読了（✓ バッジ）
 *
 * `meta.json` に未設定の既存エントリは `view_count` から派生する（0 → unread / >0 → reading）。
 * 詳細は API 仕様書 §2.4 / §2.6 / §2.7。
 */
export type ReadState = 'unread' | 'reading' | 'done';

type GeneratedBookMetaEntry = components['schemas']['BookMetaEntryOut'];

/**
 * 書籍メタデータ（1冊分）。
 * API は未設定値を除外するため、生成型の各フィールドを optional / non-null に正規化する。
 */
export type BookMetaEntry = {
    [K in keyof GeneratedBookMetaEntry]?: NonNullable<GeneratedBookMetaEntry[K]>;
};

/**
 * meta.json 全体（キー: "{path}/{filename}" または "{filename}"）
 */
export type BookMetaMap = Record<string, BookMetaEntry>;

/** サムネイル一括再生成APIレスポンス */
export type RegenerateThumbnailBulkResponse =
    components['schemas']['RegenerateThumbnailBulkResponse'];

/** PDF結合APIレスポンス */
export type MergePdfsResponse = components['schemas']['MergePdfsResponse'];

/**
 * シリーズ一括登録ダイアログ用のシリーズ選択肢。
 * `useBookMeta.allSeriesWithStats` の各エントリがこの型を満たす。
 */
export interface ExistingSeriesOption {
    id: string;
    title: string;
    /** そのシリーズの現在の最大 series_index（一括追加時の採番開始用） */
    maxIndex: number;
}

/**
 * 既存シリーズへの紐付け候補（A-1）。
 * `POST /api/series/suggest` のレスポンスに含まれる各候補。
 */
export type SuggestedSeries = components['schemas']['SuggestedSeriesOut'];
