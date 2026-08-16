import { useEffect, useState } from 'react';
import { CheckCircle2, Clock3, ImageIcon, Loader2, RotateCcw, ScanLine } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';

import { KindlePageShell } from '@/components/kindle/KindlePageShell';
import {
    jobErrorGuidance,
    jobStatusDescription,
    jobStatusLabel,
} from '@/components/kindle/kindle-labels';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import { useKindleCaptureJobs } from '@/features/kindle/queries';
import type { KindleCaptureJob } from '@/features/kindle/types';
import { formatDateTimeJa } from '@/utils/date';
import { errorMessage } from '@/utils/error';

function statusClass(status: string): string {
    if (status === 'succeeded') {
        return 'bg-green-50 text-green-700 dark:bg-green-900/30 dark:text-green-300';
    }
    if (status === 'failed') {
        return 'bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-300';
    }
    if (
        ['locating_book', 'downloading', 'positioning', 'capturing', 'awaiting_files'].includes(
            status,
        )
    ) {
        return 'bg-primary-50 text-primary-700 dark:bg-primary-900/30 dark:text-primary-300';
    }
    return 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300';
}

function elapsedLabel(start: string, end: string | null, now: number): string {
    const startTime = new Date(start).getTime();
    const endTime = end ? new Date(end).getTime() : now;
    if (!Number.isFinite(startTime) || !Number.isFinite(endTime) || endTime < startTime) {
        return '—';
    }
    const totalSeconds = Math.floor((endTime - startTime) / 1000);
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    if (hours > 0) return `${hours}時間${minutes}分`;
    if (minutes > 0) return `${minutes}分${seconds}秒`;
    return `${seconds}秒`;
}

function JobCard({
    job,
    focused,
    now,
    onRetry,
    retryDisabled,
}: {
    job: KindleCaptureJob;
    focused: boolean;
    now: number;
    onRetry: (job: KindleCaptureJob) => void;
    retryDisabled: boolean;
}) {
    const guidance = jobErrorGuidance(job.error_code);
    return (
        <article
            className={`rounded-xl border bg-white p-4 shadow-sm transition-colors dark:bg-gray-900 sm:p-5 ${
                focused
                    ? 'border-primary-500 ring-2 ring-primary-500/20'
                    : 'border-gray-200 dark:border-gray-700'
            }`}
            aria-label={`${job.title ?? job.asin} ${jobStatusLabel(job.status)}`}
        >
            <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(260px,0.7fr)]">
                <div className="min-w-0">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="min-w-0">
                            <h2 className="break-words font-semibold text-gray-900 dark:text-gray-100">
                                {job.title ?? job.asin}
                            </h2>
                            <div className="mt-1 font-mono text-xs text-gray-400">{job.asin}</div>
                        </div>
                        <span
                            className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-medium ${statusClass(job.status)}`}
                        >
                            {jobStatusLabel(job.status)}
                        </span>
                    </div>
                    <p className="mt-3 text-sm text-gray-600 dark:text-gray-300">
                        {jobStatusDescription(job.status)}
                    </p>
                    <dl className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
                        <div>
                            <dt className="text-xs text-gray-500 dark:text-gray-400">登録先</dt>
                            <dd className="mt-1 font-medium">
                                {job.source === 'comic' ? '漫画' : '小説'}
                            </dd>
                        </div>
                        <div>
                            <dt className="text-xs text-gray-500 dark:text-gray-400">ページ送り</dt>
                            <dd className="mt-1 font-medium">
                                {job.direction === 'left' ? '左送り' : '右送り'}
                            </dd>
                        </div>
                        <div>
                            <dt className="text-xs text-gray-500 dark:text-gray-400">
                                エージェント
                            </dt>
                            <dd className="mt-1 break-all font-medium">
                                {job.agent_id ?? '取得待ち'}
                            </dd>
                        </div>
                    </dl>
                </div>

                <dl className="grid grid-cols-2 gap-3 rounded-lg bg-gray-50 p-3 text-sm dark:bg-gray-800/70">
                    <div>
                        <dt className="flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400">
                            <Clock3 className="h-3.5 w-3.5" />
                            経過時間
                        </dt>
                        <dd className="mt-1 font-semibold">
                            {elapsedLabel(
                                job.started_at ?? job.requested_at,
                                job.completed_at,
                                now,
                            )}
                        </dd>
                    </div>
                    <div>
                        <dt className="flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400">
                            <ImageIcon className="h-3.5 w-3.5" />
                            撮影済み
                        </dt>
                        <dd className="mt-1 font-semibold">
                            {job.captured_screens?.toLocaleString() ?? 0} 画面
                        </dd>
                    </div>
                    <div>
                        <dt className="text-xs text-gray-500 dark:text-gray-400">依頼日時</dt>
                        <dd className="mt-1">{formatDateTimeJa(job.requested_at)}</dd>
                    </div>
                    <div>
                        <dt className="text-xs text-gray-500 dark:text-gray-400">完了日時</dt>
                        <dd className="mt-1">
                            {job.completed_at ? formatDateTimeJa(job.completed_at) : '—'}
                        </dd>
                    </div>
                </dl>
            </div>

            {job.status === 'succeeded' && (
                <Alert variant="success" className="mt-4">
                    <div className="flex items-center gap-2 font-medium">
                        <CheckCircle2 className="h-4 w-4" />
                        Pic2PDFViewerへの登録が完了しました
                    </div>
                    {job.book_id && <p className="mt-1 break-all">{job.book_id}</p>}
                </Alert>
            )}

            {job.status === 'failed' && (
                <div className="mt-4">
                    <Alert variant="error">
                        <div className="font-medium">
                            {job.error_message ?? '処理中にエラーが発生しました'}
                        </div>
                        {job.error_code && (
                            <div className="mt-1 font-mono text-xs">{job.error_code}</div>
                        )}
                        {guidance && <p className="mt-2">{guidance}</p>}
                    </Alert>
                    <Button
                        variant="secondary"
                        className="mt-3"
                        disabled={retryDisabled}
                        onClick={() => onRetry(job)}
                    >
                        <RotateCcw className="h-4 w-4" />
                        同じ条件で再実行
                    </Button>
                </div>
            )}
        </article>
    );
}

export function KindleCaptureScreen() {
    const [searchParams, setSearchParams] = useSearchParams();
    const capture = useKindleCaptureJobs();
    const [retryJob, setRetryJob] = useState<KindleCaptureJob | null>(null);
    const [now, setNow] = useState(() => Date.now());
    const focusedJobId = searchParams.get('job');

    useEffect(() => {
        const timer = window.setInterval(() => setNow(Date.now()), 1000);
        return () => window.clearInterval(timer);
    }, []);

    const retry = async () => {
        if (!retryJob || capture.creatingCaptureJob) return;
        try {
            const job = await capture.createCaptureJob({
                asin: retryJob.asin,
                source: retryJob.source,
                direction: retryJob.direction,
                expectedScreens: retryJob.expected_screens ?? undefined,
            });
            toast.success('再実行ジョブを作成しました');
            setRetryJob(null);
            setSearchParams({ job: job.id }, { replace: true });
        } catch (error) {
            toast.error(errorMessage(error, '再実行ジョブを作成できませんでした'));
        }
    };

    const retryMessage = retryJob
        ? [
              `対象: ${retryJob.title ?? retryJob.asin}`,
              `登録先: ${retryJob.source === 'comic' ? '漫画' : '小説'}`,
              `ページ送り: ${retryJob.direction === 'left' ? '左送り' : '右送り'}`,
              '',
              '原因を解消し、Kindleを起動・ログインした状態で実行してください。',
              '完了するまでWindows端末を操作しないでください。',
          ].join('\n')
        : '';

    return (
        <>
            <KindlePageShell
                title="Kindle キャプチャ"
                description="自動撮影の現在工程、進捗、結果を確認します"
            >
                {capture.error && (
                    <Alert variant="error">
                        {errorMessage(capture.error, 'キャプチャジョブを取得できませんでした')}
                    </Alert>
                )}

                <section className="mt-4">
                    <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
                        <div>
                            <div className="flex items-center gap-2">
                                <ScanLine className="h-5 w-5" />
                                <h2 className="text-lg font-semibold">撮影ジョブ</h2>
                            </div>
                            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                                状態を5秒間隔で更新します。撮影中はWindows端末を操作しないでください。
                            </p>
                        </div>
                        <div className="text-sm text-gray-500 dark:text-gray-400">
                            {capture.jobs.length.toLocaleString()} 件
                        </div>
                    </div>

                    {capture.isLoading ? (
                        <div className="flex items-center justify-center gap-2 rounded-xl border border-gray-200 bg-white py-16 text-sm text-gray-500 dark:border-gray-700 dark:bg-gray-900">
                            <Loader2 className="h-5 w-5 animate-spin" />
                            ジョブを読み込み中
                        </div>
                    ) : capture.jobs.length === 0 ? (
                        <div className="rounded-xl border border-dashed border-gray-300 bg-white py-16 text-center dark:border-gray-700 dark:bg-gray-900">
                            <ScanLine className="mx-auto h-8 w-8 text-gray-400" />
                            <p className="mt-2 text-sm text-gray-500">
                                キャプチャジョブはありません。
                            </p>
                            <p className="mt-1 text-xs text-gray-400">
                                購入書籍の詳細から「撮影して取り込む」を選択してください。
                            </p>
                        </div>
                    ) : (
                        <div className="space-y-3">
                            {capture.jobs.map((job) => (
                                <JobCard
                                    key={job.id}
                                    job={job}
                                    focused={job.id === focusedJobId}
                                    now={now}
                                    onRetry={setRetryJob}
                                    retryDisabled={capture.creatingCaptureJob}
                                />
                            ))}
                        </div>
                    )}
                </section>
            </KindlePageShell>

            <ConfirmDialog
                open={retryJob !== null}
                title="新しいジョブとして再実行しますか？"
                message={retryMessage}
                confirmLabel="再実行ジョブを作成"
                confirmDisabled={capture.creatingCaptureJob}
                onConfirm={() => void retry()}
                onCancel={() => setRetryJob(null)}
            />
        </>
    );
}
