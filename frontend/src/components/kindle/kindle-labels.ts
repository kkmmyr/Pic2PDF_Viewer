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
    claimed: 'エージェント接続済み',
    locating_book: '書籍を検索中',
    downloading: '書籍をダウンロード中',
    positioning: '先頭位置へ移動中',
    waiting_user: '書籍を開くまで待機（旧方式）',
    capturing: '撮影中',
    awaiting_files: '転送・登録中',
    succeeded: '取込完了',
    failed: '失敗',
    cancelled: 'キャンセル',
};

export const JOB_STATUS_DESCRIPTIONS: Record<string, string> = {
    queued: 'Windowsエージェントがジョブを取得するまで待機しています。',
    claimed: 'Windowsエージェントが処理を開始しました。',
    locating_book: 'KindleライブラリでASINを照合しています。',
    downloading: 'Kindle書籍の取得とファイル安定を待っています。',
    positioning: '読書画面を表紙または先頭位置へ戻しています。',
    waiting_user: '旧エージェントが利用者の操作を待っています。',
    capturing: '表紙または先頭から最終ページまで撮影しています。',
    awaiting_files: '画像を検証し、Pic2PDFViewerへ登録しています。',
    succeeded: '画像とASINの登録が完了しました。',
    failed: '安全に処理を停止しました。原因を確認して再実行してください。',
    cancelled: '処理はキャンセルされました。',
};

export const JOB_ERROR_GUIDANCE: Record<string, string> = {
    kindle_not_running: 'Kindleアプリを起動し、ライブラリを表示してから再実行してください。',
    kindle_ui_unavailable: 'Kindleのログイン状態と確認ダイアログの有無を確認してください。',
    kindle_app_exited: 'Kindleが終了しました。再起動してから新しいジョブを作成してください。',
    book_not_found: '対象書籍が購入済みライブラリにあることを確認してください。',
    book_match_ambiguous: '同じ書籍候補が複数あります。Kindleライブラリの状態を確認してください。',
    book_identity_unverified: 'ASIN・タイトル・著者・巻の照合情報を確認してください。',
    download_failed: 'Kindleの通信状態と空き容量を確認してください。',
    download_timeout: 'ダウンロード完了後に新しいジョブとして再実行してください。',
    positioning_failed: '読書画面を閉じ、ライブラリへ戻してから再実行してください。',
    capture_failed: 'Kindleを前面表示し、端末を操作せずに再実行してください。',
    transfer_failed: 'Samba共有とWindows側の接続状態を確認してください。',
    registration_failed: 'サーバーの受信箱と同名書籍の有無を確認してください。',
    agent_heartbeat_timeout: 'エージェントを再起動し、新しいジョブとして再実行してください。',
    agent_restart_requires_new_job:
        '途中ジョブは再開しません。新しいジョブとして再実行してください。',
};

export function bookTypeLabel(value: string): string {
    return BOOK_TYPE_LABELS[value] ?? value;
}

export function jobStatusLabel(value: string): string {
    return JOB_STATUS_LABELS[value] ?? value;
}

export function jobStatusDescription(value: string): string {
    return JOB_STATUS_DESCRIPTIONS[value] ?? '状態を確認しています。';
}

export function jobErrorGuidance(value: string | null): string | null {
    return value ? (JOB_ERROR_GUIDANCE[value] ?? null) : null;
}
