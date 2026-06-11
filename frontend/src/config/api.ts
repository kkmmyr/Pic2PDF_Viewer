/**
 * API設定
 * 本番ビルド時は同一オリジン配信（dist 統合モード）のため空文字。
 * 開発時は VITE_API_URL または localhost:8000 を使用。
 */
export const API_CONFIG = {
    BASE_URL: import.meta.env.PROD ? '' : import.meta.env.VITE_API_URL || 'http://localhost:8766',
} as const;

import { LibrarySource } from '@/types';

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
    BOOK_IMAGES: (path: string, source: LibrarySource = 'doujin') =>
        `/api/books/${encodeURIComponent(path)}/images?source=${source}`,
    /** ページ削除 */
    DELETE_PAGES: (filename: string, path: string, source: LibrarySource = 'doujin') =>
        `/api/pdfs/${encodeURIComponent(filename)}/delete_pages?path=${encodeURIComponent(path || '')}&source=${source}`,
    /** ページ並び替え（B-3） */
    REORDER_PAGES: (filename: string, path: string, source: LibrarySource = 'doujin') =>
        `/api/pdfs/${encodeURIComponent(filename)}/reorder_pages?path=${encodeURIComponent(path || '')}&source=${source}`,
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
    /** メタデータ一括エクスポート（JSON ダウンロード） */
    META_EXPORT: (source: string) => `/api/meta/export?source=${encodeURIComponent(source)}`,
    /** 閲覧記録（カウント+1） */
    META_VIEW: '/api/meta/view',
    /** サムネイル一括再生成 */
    REGENERATE_THUMBNAIL_BULK: '/api/thumbnails/regenerate_bulk',
    /** PDF結合 */
    MERGE_PDFS: '/api/pdfs/merge',
    /** PDF完全削除（非表示書籍専用） */
    DELETE_PDFS: '/api/pdfs',
    /** シリーズ手動割り当て */
    SERIES_ASSIGN: '/api/series/assign',
    /** シリーズ手動解除 */
    SERIES_UNASSIGN: '/api/series/unassign',
    /** シリーズ巻数の並べ替え（DnD） */
    SERIES_REORDER: '/api/series/reorder',
    /** 既存シリーズへの紐付け候補提案（A-1） */
    SERIES_SUGGEST: '/api/series/suggest',
    /** hitomi.la 新着一覧取得 */
    HITOMI_NEW_ARRIVALS: '/api/hitomi/new-arrivals',
    /** hitomi.la 新着個別既読化 */
    HITOMI_DISMISS: (id: number) => `/api/hitomi/dismiss/${id}`,
    /** hitomi.la 新着一括既読化 */
    HITOMI_DISMISS_ALL: '/api/hitomi/dismiss-all',
    /** hitomi.la 監視対象一覧 */
    HITOMI_WATCHLIST: '/api/hitomi/watchlist',
    /** hitomi.la 監視対象削除 */
    HITOMI_WATCHLIST_DELETE: (normalized: string, language: string = 'japanese') =>
        `/api/hitomi/watchlist/${encodeURIComponent(normalized)}?language=${encodeURIComponent(language)}`,
    /** hitomi.la 監視スクリプトを同期実行 */
    HITOMI_RUN_NOW: '/api/hitomi/run-now',
    /** ジャンルリスト取得・追加・削除 */
    GENRES: '/api/genres',
    /** ジャンル並べ替え */
    GENRES_REORDER: '/api/genres/reorder',
    /** Amazon CSV 固定パスインポート（authors/asin 空欄補完） */
    AMAZON_IMPORT: (source: string) => `/api/amazon/import?source=${encodeURIComponent(source)}`,
    /** UI プリファレンス（フィルター + ピン）取得 */
    PREFS: (source: string) => `/api/prefs?source=${encodeURIComponent(source)}`,
    /** UI フィルター更新 */
    PREFS_FILTERS: '/api/prefs/filters',
    /** グループピン登録 / 上書き */
    PREFS_PINS: '/api/prefs/pins',
    /** 指定ページのサムネイル画像をオンデマンド生成（ページスライダー / 編集モードグリッド用） */
    PAGE_THUMBNAIL: (
        name: string,
        page: number,
        path: string,
        source: LibrarySource,
        width = 400,
        version?: number,
    ) => {
        const versionParam = version !== undefined ? `&v=${version}` : '';
        return `/api/thumbnails/page?name=${encodeURIComponent(name)}&page=${page}&path=${encodeURIComponent(path)}&source=${source}&width=${width}${versionParam}`;
    },
} as const;

/**
 * 静的ファイルパス
 */
export const STATIC_PATHS = {
    /** PDFファイルパス */
    PDF: (path: string, filename: string, source: LibrarySource = 'doujin', version?: number) => {
        const basePath = path ? '/' + path.split('/').map(encodeURIComponent).join('/') : '';
        const encodedFilename = encodeURIComponent(filename);
        const versionParam = version !== undefined ? `?v=${version}` : '';
        let prefix = '/pdfs';
        if (source === 'comic') prefix = '/comic/pdfs';

        return `${prefix}${basePath}/${encodedFilename}${versionParam}`;
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
