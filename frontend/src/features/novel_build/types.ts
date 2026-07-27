/**
 * novel_build 機能の共通型定義。
 * バックエンド OpenAPI 生成型を正本とする。
 */
import type { components } from '@/types/api';

export type BuildMode = components['schemas']['EnqueueRequest']['mode'];
export type BuildJob = components['schemas']['BuildRunningJobOut'];
export type QueuedBuildJob = components['schemas']['BuildQueuedJobOut'];
export type FinishedJob = components['schemas']['BuildFinishedJobOut'];
export type BuildQueueStatus = components['schemas']['BuildStatusResponse'];

export interface BuildStreamHandlers {
    onStatus: (status: BuildQueueStatus) => void;
    onError: (error: Event) => void;
}
