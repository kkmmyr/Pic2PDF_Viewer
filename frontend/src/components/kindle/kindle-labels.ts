import type { KindleCatalogBook } from '@/types/kindleCatalog';

export const OWNERSHIP_LABELS: Record<KindleCatalogBook['ownership'], string> = {
    purchased: '購入',
    borrowed_active: 'KU借用中',
    borrowed_ended: 'KU終了',
    returned: '返品',
    unknown: '不明',
};

export const CAPTURE_LABELS: Record<KindleCatalogBook['capture_state'], string> = {
    not_captured: '画像なし',
    captured: '取込済み',
    multiple_links: '重複確認',
    capture_pending: '取込中',
};

export const BOOK_TYPE_LABELS: Record<string, string> = {
    comic: '漫画',
    novel: '小説',
    other: 'その他',
    unknown: '未分類',
};

export const JOB_STATUS_LABELS: Record<string, string> = {
    queued: '待機中',
    claimed: 'エージェント確認中',
    waiting_user: '書籍を開くまで待機',
    capturing: '撮影中',
    awaiting_files: 'ファイル転送待ち',
    completed: '完了',
    failed: '失敗',
    cancelled: 'キャンセル',
};

export function bookTypeLabel(value: string): string {
    return BOOK_TYPE_LABELS[value] ?? value;
}

export function jobStatusLabel(value: string): string {
    return JOB_STATUS_LABELS[value] ?? value;
}
