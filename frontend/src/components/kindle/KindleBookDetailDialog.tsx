import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';

import {
    bookTypeLabel,
    CAPTURE_LABELS,
    jobStatusLabel,
    OWNERSHIP_LABELS,
} from '@/components/kindle/kindle-labels';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import {
    Dialog,
    DialogBody,
    DialogFooter,
    DialogCancelButton,
    DialogPrimaryButton,
} from '@/components/ui/dialog';
import { useKindleCaptureJobs } from '@/hooks/useKindleCatalog';
import type { KindleCatalogBook } from '@/types/kindleCatalog';
import { formatDateJa } from '@/utils/date';
import { errorMessage } from '@/utils/error';

interface KindleBookDetailDialogProps {
    book: KindleCatalogBook | null;
    onClose: () => void;
}

type CaptureSource = 'comic' | 'novel';
type PageDirection = 'left' | 'right';

const ACTIVE_JOB_STATUSES = new Set([
    'queued',
    'claimed',
    'locating_book',
    'downloading',
    'positioning',
    'waiting_user',
    'capturing',
    'awaiting_files',
]);

function initialSource(book: KindleCatalogBook | null): CaptureSource {
    return book?.book_type === 'novel' ? 'novel' : 'comic';
}

function DetailItem({ label, value }: { label: string; value: string }) {
    return (
        <div>
            <dt className="text-xs font-medium text-gray-500 dark:text-gray-400">{label}</dt>
            <dd className="mt-1 text-sm text-gray-900 dark:text-gray-100">{value || '—'}</dd>
        </div>
    );
}

export function KindleBookDetailDialog({ book, onClose }: KindleBookDetailDialogProps) {
    const navigate = useNavigate();
    const capture = useKindleCaptureJobs({ enabled: book !== null });
    const [source, setSource] = useState<CaptureSource>(initialSource(book));
    const [direction, setDirection] = useState<PageDirection>('left');
    const [confirmOpen, setConfirmOpen] = useState(false);

    useEffect(() => {
        setSource(initialSource(book));
        setDirection('left');
        setConfirmOpen(false);
    }, [book]);

    const activeJob = book
        ? capture.jobs.find((job) => job.asin === book.asin && ACTIVE_JOB_STATUSES.has(job.status))
        : undefined;
    const alreadyCaptured = book?.capture_state === 'captured';
    const startDisabled = capture.creatingCaptureJob || activeJob !== undefined || alreadyCaptured;

    const openCapturePage = (jobId?: string) => {
        onClose();
        navigate(jobId ? `/kindle/capture?job=${encodeURIComponent(jobId)}` : '/kindle/capture');
    };

    const createJob = async () => {
        if (!book || startDisabled) return;
        try {
            const job = await capture.createCaptureJob({
                asin: book.asin,
                source,
                direction,
            });
            toast.success('Kindle撮影ジョブを作成しました');
            setConfirmOpen(false);
            openCapturePage(job.id);
        } catch (error) {
            toast.error(errorMessage(error, 'Kindle撮影ジョブを作成できませんでした'));
        }
    };

    const confirmationMessage = book
        ? [
              `対象: ${book.title}`,
              `ASIN: ${book.asin}`,
              `登録先: ${source === 'comic' ? '漫画' : '小説'}`,
              `ページ送り: ${direction === 'left' ? '左送り' : '右送り'}`,
              '',
              '・Kindleアプリを起動し、ログインしておく',
              '・Windowsの画面ロックを解除しておく',
              '・完了するまでマウスとキーボードを操作しない',
              '・撮影後の読書位置は最終ページになります',
          ].join('\n')
        : '';

    return (
        <>
            <Dialog
                open={book !== null}
                title={book?.title ?? '書籍詳細'}
                subtitle={book?.asin}
                maxWidth="md"
                onClose={onClose}
            >
                <DialogBody className="max-h-[70vh] space-y-5 overflow-y-auto">
                    {book && (
                        <>
                            <dl className="grid grid-cols-2 gap-4">
                                <DetailItem
                                    label="著者"
                                    value={book.authors.join(' / ') || '著者不明'}
                                />
                                <DetailItem label="種別" value={bookTypeLabel(book.book_type)} />
                                <DetailItem
                                    label="所有状態"
                                    value={OWNERSHIP_LABELS[book.ownership]}
                                />
                                <DetailItem
                                    label="画像状態"
                                    value={CAPTURE_LABELS[book.capture_state]}
                                />
                                <DetailItem label="シリーズ" value={book.series_name ?? '—'} />
                                <DetailItem
                                    label="巻"
                                    value={
                                        book.volume_label ?? book.volume_number?.toString() ?? '—'
                                    }
                                />
                                <DetailItem label="出版社" value={book.publisher ?? '—'} />
                                <DetailItem
                                    label="Kindle取得日"
                                    value={formatDateJa(book.kindle_acquisition_date) || '—'}
                                />
                            </dl>

                            <section className="rounded-lg border border-gray-200 p-4 dark:border-gray-700">
                                <h3 className="text-sm font-semibold">撮影条件</h3>
                                <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                                    カタログの種別が誤っている場合は、実際の内容に合わせて変更してください。
                                </p>
                                <div className="mt-3 grid gap-3 sm:grid-cols-2">
                                    <label className="text-sm">
                                        <span className="mb-1 block font-medium">登録先</span>
                                        <select
                                            aria-label="撮影後の登録先"
                                            value={source}
                                            onChange={(event) =>
                                                setSource(event.target.value as CaptureSource)
                                            }
                                            className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 dark:border-gray-600 dark:bg-gray-800"
                                        >
                                            <option value="comic">漫画</option>
                                            <option value="novel">小説</option>
                                        </select>
                                    </label>
                                    <label className="text-sm">
                                        <span className="mb-1 block font-medium">ページ送り</span>
                                        <select
                                            aria-label="ページ送り方向"
                                            value={direction}
                                            onChange={(event) =>
                                                setDirection(event.target.value as PageDirection)
                                            }
                                            className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 dark:border-gray-600 dark:bg-gray-800"
                                        >
                                            <option value="left">左送り（右開き・縦書き）</option>
                                            <option value="right">右送り（左開き・横書き）</option>
                                        </select>
                                    </label>
                                </div>
                            </section>

                            {activeJob && (
                                <Alert variant="warning">
                                    <div className="font-medium">
                                        この書籍は{jobStatusLabel(activeJob.status)}です
                                    </div>
                                    <p className="mt-1">
                                        同じASINの処理中ジョブがあるため、新しいジョブは作成できません。
                                    </p>
                                    <Button
                                        variant="secondary"
                                        size="sm"
                                        className="mt-3"
                                        onClick={() => openCapturePage(activeJob.id)}
                                    >
                                        既存ジョブを確認
                                    </Button>
                                </Alert>
                            )}

                            {alreadyCaptured && !activeJob && (
                                <Alert variant="info">
                                    この書籍は取込済みです。上書き撮影は初期版の対象外です。
                                </Alert>
                            )}
                        </>
                    )}
                </DialogBody>
                <DialogFooter>
                    <DialogCancelButton onClick={onClose} disabled={capture.creatingCaptureJob}>
                        閉じる
                    </DialogCancelButton>
                    <DialogPrimaryButton
                        onClick={() => setConfirmOpen(true)}
                        disabled={startDisabled}
                    >
                        {capture.creatingCaptureJob ? '作成中…' : '撮影して取り込む'}
                    </DialogPrimaryButton>
                </DialogFooter>
            </Dialog>

            <ConfirmDialog
                open={confirmOpen}
                title="Kindle撮影を開始しますか？"
                message={confirmationMessage}
                confirmLabel="ジョブを作成"
                confirmDisabled={capture.creatingCaptureJob}
                onConfirm={() => void createJob()}
                onCancel={() => setConfirmOpen(false)}
            />
        </>
    );
}
