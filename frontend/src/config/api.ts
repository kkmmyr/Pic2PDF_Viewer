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
    /** PDFリネーム */
    RENAME: '/api/rename',
    /** サムネイル再生成 */
    REGENERATE_THUMBNAIL: '/api/thumbnails/regenerate',
    /** OCR機能 */
    OCR_RUN: '/api/ocr/run',
    OCR_STOP: '/api/ocr/stop',
    OCR_STATUS: '/api/ocr/status',
    /** 既存PDFの一括圧縮 */
    BATCH_COMPRESS: '/api/batch_compress',
    /** Generate ジョブ進捗取得 */
    GENERATE_JOB: (jobId: string) => `/api/generate/job/${jobId}`,
    /** 書籍メタデータ取得・更新 */
    META: '/api/meta',
    /** 閲覧記録（カウント+1） */
    META_VIEW: '/api/meta/view',
    /** 作者名自動登録ジョブ開始 */
    META_AUTO_FILL: '/api/meta/auto-fill',
    /** 作者名自動登録ジョブ進捗取得 */
    META_AUTO_FILL_STATUS: '/api/meta/auto-fill/status',
    /** サムネイル一括再生成 */
    REGENERATE_THUMBNAIL_BULK: '/api/thumbnails/regenerate_bulk',
    /** PDF結合 */
    MERGE_PDFS: '/api/pdfs/merge',
} as const;

/**
 * 静的ファイルパス
 */
export const STATIC_PATHS = {
    /** PDFファイルパス */
    PDF: (path: string, filename: string, source: LibrarySource = 'generated', version?: number) => {
        const basePath = path ? `/${path}` : '';
        const versionParam = version !== undefined ? `?v=${version}` : '';
        let prefix = '/pdfs';
        if (source === 'kindle') prefix = '/kindle/pdfs';
        else if (source === 'novel') prefix = '/kindle_novel/pdfs';

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
