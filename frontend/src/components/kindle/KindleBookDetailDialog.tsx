import { Alert } from '@/components/ui/alert';
import { Dialog, DialogBody, DialogFooter, DialogCancelButton } from '@/components/ui/dialog';
import { bookTypeLabel, CAPTURE_LABELS, OWNERSHIP_LABELS } from '@/components/kindle/kindle-labels';
import type { KindleCatalogBook } from '@/types/kindleCatalog';
import { formatDateJa } from '@/utils/date';

interface KindleBookDetailDialogProps {
    book: KindleCatalogBook | null;
    onClose: () => void;
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
    return (
        <Dialog
            open={book !== null}
            title={book?.title ?? '書籍詳細'}
            subtitle={book?.asin}
            maxWidth="md"
            onClose={onClose}
        >
            <DialogBody className="space-y-5">
                {book && (
                    <>
                        <dl className="grid grid-cols-2 gap-4">
                            <DetailItem
                                label="著者"
                                value={book.authors.join(' / ') || '著者不明'}
                            />
                            <DetailItem label="種別" value={bookTypeLabel(book.book_type)} />
                            <DetailItem label="所有状態" value={OWNERSHIP_LABELS[book.ownership]} />
                            <DetailItem
                                label="画像状態"
                                value={CAPTURE_LABELS[book.capture_state]}
                            />
                            <DetailItem label="シリーズ" value={book.series_name ?? '—'} />
                            <DetailItem
                                label="巻"
                                value={book.volume_label ?? book.volume_number?.toString() ?? '—'}
                            />
                            <DetailItem label="出版社" value={book.publisher ?? '—'} />
                            <DetailItem
                                label="Kindle取得日"
                                value={formatDateJa(book.kindle_acquisition_date) || '—'}
                            />
                        </dl>
                        <Alert variant="warning">
                            <div className="font-medium">キャプチャは利用準備中です</div>
                            <p className="mt-1">
                                Samba共有とエージェントトークンの運用設定が完了するまで、新規ジョブは作成できません。
                            </p>
                        </Alert>
                    </>
                )}
            </DialogBody>
            <DialogFooter>
                <DialogCancelButton onClick={onClose}>閉じる</DialogCancelButton>
            </DialogFooter>
        </Dialog>
    );
}
