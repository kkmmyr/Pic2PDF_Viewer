/**
 * PDFファイル情報
 */
export interface PdfFile {
    name: string;
    thumbnail: string | null;
    created_at: number;
}

/**
 * 書籍画像APIレスポンス
 */
export interface BookImagesResponse {
    images: string[];
}

/**
 * ページ削除APIレスポンス
 */
export interface DeletePagesResponse {
    message: string;
    total_pages: number;
}

/**
 * ステータスアイテム
 */
export interface StatusItem {
    name: string;
    type: string;
    status: 'not_started' | 'in_progress' | 'completed';
}

/**
 * ステータスAPIレスポンス
 */
export interface StatusResponse {
    items: StatusItem[];
}

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
export type LibrarySource = 'generated' | 'kindle' | 'novel';

/**
 * Generator ジョブステータス
 */
export type GenerateJobStatus = 'pending' | 'running' | 'completed' | 'failed';

export interface GenerateJob {
    job_id: string;
    status: GenerateJobStatus;
    /** 現在処理中のアイテム名 */
    current_item: string | null;
    /** 生成済みファイル一覧（完了後に設定） */
    files: string[];
    message: string;
    error: string | null;
}

/**
 * 並び替え順序
 */
export type SortOrder = 'name_asc' | 'name_desc' | 'date_asc' | 'date_desc' | 'favorites_first' | 'view_desc' | 'recent_view';

/**
 * 書籍メタデータ（1冊分）
 */
export interface BookMetaEntry {
    authors: string[];
    tags?: string[];
    view_count?: number;
    last_viewed_at?: number;
    /** シリーズ識別子（同シリーズで共通） */
    series_id?: string;
    /** シリーズ表示名（共通プレフィックス） */
    series_title?: string;
    /** シリーズ内の巻数 (1 始まり) */
    series_index?: number;
    /** 非表示フラグ。true なら通常モードでは一覧・検索・フィルタに表示されない */
    hidden?: boolean;
    /** ジャンル（例: "プリンセスコネクト" / "Voiceloid" / "オリジナル"） */
    genre?: string;
}

/**
 * meta.json 全体（キー: "{path}/{filename}" または "{filename}"）
 */
export type BookMetaMap = Record<string, BookMetaEntry>;

/**
 * サムネイル一括再生成APIレスポンス
 */
export interface RegenerateThumbnailBulkResponse {
    message: string;
    succeeded: string[];
    failed: string[];
}

/**
 * PDF結合APIレスポンス
 */
export interface MergePdfsResponse {
    message: string;
    output_name: string;
    total_pages: number;
}

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
