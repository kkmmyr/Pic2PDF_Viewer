/**
 * API設定
 * 開発環境と本番環境で切り替え可能
 */
export const API_CONFIG = {
    BASE_URL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
} as const;

/**
 * APIエンドポイント
 */
export const API_ENDPOINTS = {
    /** PDF一覧取得 */
    PDFS: '/api/pdfs',
    /** PDF生成 */
    GENERATE: '/api/generate',
    /** ステータス取得 */
    STATUS: '/api/status',
    /** 書籍画像取得 */
    BOOK_IMAGES: (path: string) => `/api/books/${encodeURIComponent(path)}/images`,
    /** ページ削除 */
    DELETE_PAGES: (filename: string, path: string) =>
        `/api/pdfs/${filename}/delete_pages?path=${path}`,
} as const;

/**
 * 静的ファイルパス
 */
export const STATIC_PATHS = {
    /** PDFファイルパス */
    PDF: (path: string, filename: string, version?: number) => {
        const basePath = path ? `/${path}` : '';
        const versionParam = version !== undefined ? `?v=${version}` : '';
        return `/pdfs${basePath}/${filename}${versionParam}`;
    },
    /** サムネイルパス */
    THUMBNAIL: (path: string) => path,
    /** 画像パス */
    IMAGE: (path: string) => path,
} as const;

/**
 * API URLを構築するヘルパー関数
 */
export function buildApiUrl(endpoint: string): string {
    return `${API_CONFIG.BASE_URL}${endpoint}`;
}

/**
 * 静的ファイルURLを構築するヘルパー関数
 */
export function buildStaticUrl(path: string): string {
    return `${API_CONFIG.BASE_URL}${path}`;
}
