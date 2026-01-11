/**
 * API設定
 * 開発環境と本番環境で切り替え可能
 */
export const API_CONFIG = {
    BASE_URL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
} as const;

import { LibrarySource } from '../types';

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
    BOOK_IMAGES: (path: string, source: LibrarySource = 'generated') =>
        `/api/books/${path}/images?source=${source}`,
    /** ページ削除 */
    DELETE_PAGES: (filename: string, path: string, source: LibrarySource = 'generated') =>
        `/api/pdfs/${filename}/delete_pages?path=${path || ''}&source=${source}`,
    /** ディレクトリ一覧取得 */
    DIRECTORIES: '/api/directories',
    /** ファイル/ディレクトリ移動 */
    MOVE: '/api/move',
} as const;

/**
 * 静的ファイルパス
 */
export const STATIC_PATHS = {
    /** PDFファイルパス */
    PDF: (path: string, filename: string, source: LibrarySource = 'generated', version?: number) => {
        const basePath = path ? `/${path}` : '';
        const versionParam = version !== undefined ? `?v=${version}` : '';
        const prefix = source === 'kindle' ? '/kindle/pdfs' : '/pdfs';
        return `${prefix}${basePath}/${filename}${versionParam}`;
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
