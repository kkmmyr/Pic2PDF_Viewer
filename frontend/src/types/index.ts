/**
 * PDFファイル情報
 */
export interface PdfFile {
    name: string;
    thumbnail: string | null;
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
}

/**
 * PDF生成APIレスポンス
 */
export interface GenerateResponse {
    message: string;
    files: string[];
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
export type LibrarySource = 'generated' | 'kindle';
