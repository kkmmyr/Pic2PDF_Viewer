import { AlertTriangle, Loader2, ScanLine } from 'lucide-react';

import { KindlePageShell } from '@/components/kindle/KindlePageShell';
import { jobStatusLabel } from '@/components/kindle/kindle-labels';
import { Alert } from '@/components/ui/alert';
import { useKindleCaptureJobs } from '@/hooks/useKindleCatalog';
import { formatDateTimeJa } from '@/utils/date';
import { errorMessage } from '@/utils/error';

function statusClass(status: string): string {
    if (status === 'completed') {
        return 'bg-green-50 text-green-700 dark:bg-green-900/30 dark:text-green-300';
    }
    if (status === 'failed') {
        return 'bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-300';
    }
    if (status === 'capturing' || status === 'awaiting_files') {
        return 'bg-primary-50 text-primary-700 dark:bg-primary-900/30 dark:text-primary-300';
    }
    return 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300';
}

export default function KindleCapturePage() {
    const capture = useKindleCaptureJobs();

    return (
        <KindlePageShell
            title="Kindle キャプチャ"
            description="Windowsキャプチャエージェントの準備状況と既存ジョブを確認します"
        >
            <Alert variant="warning" icon={<AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />}>
                <div className="font-medium">現在は利用準備中です</div>
                <p className="mt-1">
                    専用Samba共有とエージェントトークンの運用設定が完了するまで、新規ジョブ作成は表示しません。既存ジョブの状態は引き続き確認できます。
                </p>
            </Alert>

            {capture.error && (
                <Alert variant="error" className="mt-4">
                    {errorMessage(capture.error, 'キャプチャジョブを取得できませんでした')}
                </Alert>
            )}

            <section className="mt-4 rounded-xl border border-gray-200 bg-white p-5 dark:border-gray-700 dark:bg-gray-900">
                <div className="flex items-center gap-2">
                    <ScanLine className="h-5 w-5" />
                    <h2 className="text-lg font-semibold">既存ジョブ</h2>
                </div>
                <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                    ジョブ状態を5秒間隔で更新します。
                </p>

                {capture.isLoading ? (
                    <div className="flex items-center gap-2 py-10 text-sm text-gray-500">
                        <Loader2 className="h-4 w-4 animate-spin" />
                        ジョブを読み込み中
                    </div>
                ) : capture.jobs.length === 0 ? (
                    <div className="py-12 text-center text-sm text-gray-500">
                        キャプチャジョブはありません。
                    </div>
                ) : (
                    <div className="mt-4 space-y-3">
                        {capture.jobs.map((job) => (
                            <article
                                key={job.id}
                                className="rounded-lg border border-gray-200 p-4 dark:border-gray-700"
                            >
                                <div className="flex flex-wrap items-start justify-between gap-3">
                                    <div className="min-w-0">
                                        <div className="font-medium">{job.title ?? job.asin}</div>
                                        <div className="mt-1 text-xs text-gray-500">
                                            {job.asin} / {job.source === 'comic' ? '漫画' : '小説'}{' '}
                                            / {job.direction === 'left' ? '左送り' : '右送り'}
                                        </div>
                                        <div className="mt-1 text-xs text-gray-400">
                                            依頼: {formatDateTimeJa(job.requested_at)}
                                            {job.agent_id ? ` / Agent: ${job.agent_id}` : ''}
                                        </div>
                                    </div>
                                    <span
                                        className={`rounded-full px-2.5 py-1 text-xs font-medium ${statusClass(job.status)}`}
                                    >
                                        {jobStatusLabel(job.status)}
                                    </span>
                                </div>
                                {job.error_message && (
                                    <Alert variant="error" className="mt-3">
                                        {job.error_message}
                                    </Alert>
                                )}
                            </article>
                        ))}
                    </div>
                )}
            </section>
        </KindlePageShell>
    );
}
