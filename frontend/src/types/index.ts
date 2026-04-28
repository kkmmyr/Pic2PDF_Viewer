/**
 * PDFファイル情報
 */
export interface PdfFile {
    name: string;
    thumbnail: string | null;
    created_at: number;
}

/**
 * PDF一覧APIレスポンス
 */
export interface PdfListResponse {
    files: PdfFile[];
    directories: string[];
    current_path: string;
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
 * PDF生成APIリクエスト
 */
export interface GenerateRequest {
    source_dir: string;
    generate_compressed?: boolean;
    quality?: number;
}

/**
 * PDF生成APIレスポンス（POST /api/generate）
 * ジョブが非同期で開始されたことを示す。進捗は GenerateJob でポーリングして取得する。
 */
export interface GenerateResponse {
    job_id: string;
    status: 'pending';
}

/**
 * 一括圧縮APIリクエスト
 */
export interface BatchCompressRequest {
    quality: number;
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

export interface CreateDirectoryRequest {
    path: string;
    name: string;
    source: LibrarySource;
}

export interface MoveItemsRequest {
    items: string[];
    source_path: string;
    destination_path: string;
    source: LibrarySource;
}

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
}

/**
 * meta.json 全体（キー: "{path}/{filename}" または "{filename}"）
 */
export type BookMetaMap = Record<string, BookMetaEntry>;

/**
 * メタデータ更新リクエスト。
 * authors / tags は省略可。省略されたフィールドは変更されない。
 */
export interface UpdateMetaRequest {
    path: string;
    names: string[];
    authors?: string[];
    tags?: string[];
    source: string;
}

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
