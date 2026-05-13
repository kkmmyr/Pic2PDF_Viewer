/**
 * novel_build 機能の共通型定義。
 * バックエンド API §8 スキーマと一致させる。
 */

export interface BuildJob {
    id: number;
    target_id: string | null;
    started_at?: string;
    enqueued_at?: string;
    progress_total?: number;
    progress_done?: number;
    current_step?: string | null;
}

export interface FinishedJob {
    id: number;
    target_id: string | null;
    state: 'completed' | 'failed' | 'canceled';
    finished_at: string;
    error_message: string | null;
}

export interface BuildQueueStatus {
    is_running: boolean;
    current_job: BuildJob | null;
    queued_jobs: BuildJob[];
    recent_finished: FinishedJob[];
}

export interface BuildStreamHandlers {
    onStatus: (status: BuildQueueStatus) => void;
    onError: (error: Event) => void;
}
