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
 * PDF生成APIレスポンス
 */
export interface GenerateResponse {
    message: string;
    files: string[];
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
export type SortOrder = 'name_asc' | 'name_desc' | 'date_asc' | 'date_desc' | 'favorites_first';
