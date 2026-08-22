import { useState } from 'react';
import { AlertTriangle, ExternalLink, Loader2 } from 'lucide-react';
import { Link } from 'react-router-dom';
import { toast } from 'sonner';

import { Alert } from '@/components/ui/alert';
import { Button, buttonVariants } from '@/components/ui/button';
import { useKindleCaptureQualityWarnings } from '@/features/kindle/queries';
import type {
    KindleCaptureQualityWarning,
    KindleCaptureWarningStatus,
} from '@/features/kindle/types';
import { cn } from '@/lib/utils';
import { formatDateTimeJa } from '@/utils/date';
import { errorMessage } from '@/utils/error';

const WARNING_LABELS: Record<string, { label: string; description: string }> = {
    repeated_screen_overlay_candidate: {
        label: '画面UIの重なり候補',
        description: '同じ位置に繰り返し表示されたUIや帯が写り込んだ可能性があります。',
    },
    blank_or_sparse_candidate: {
        label: '白紙・低情報量候補',
        description: '白紙に近いページです。章扉や意図的な空白ページの場合もあります。',
    },
    exact_duplicate_candidate: {
        label: '完全重複候補',
        description: '同一画像のページが複数あります。見開きや演出による正常例も含みます。',
    },
    adjacent_near_duplicate_candidate: {
        label: '隣接ページ類似候補',
        description: '前後のページがよく似ています。微差の演出や連続ページの場合もあります。',
    },
    novel_edge_content_candidate: {
        label: '小説ページ端の内容候補',
        description: 'ページ端に濃い内容があり、切れやUI混入の確認が必要です。',
    },
    low_size_candidate: {
        label: '低容量画像候補',
        description: '他ページより画像容量が小さい候補です。表紙や章扉の場合もあります。',
    },
};

const FILTERS: { value: KindleCaptureWarningStatus; label: string }[] = [
    { value: 'unread', label: '未確認' },
    { value: 'read', label: '確認済み' },
    { value: 'all', label: 'すべて' },
];

function readerPath(warning: KindleCaptureQualityWarning, page: number): string {
    if (warning.source === 'novel') {
        const bookName = warning.book_id.replace(/\.pdf$/i, '');
        return `/novel/reader/${encodeURIComponent(bookName)}?page=${page}`;
    }
    const params = new URLSearchParams({
        file: warning.book_id,
        page: String(page),
    });
    return `/comic?${params.toString()}`;
}

function WarningCard({
    warning,
    updating,
    onUpdateRead,
}: {
    warning: KindleCaptureQualityWarning;
    updating: boolean;
    onUpdateRead: (warning: KindleCaptureQualityWarning) => void;
}) {
    const [selectedPage, setSelectedPage] = useState(warning.pages[0] ?? 1);
    const copy = WARNING_LABELS[warning.code] ?? {
        label: warning.code,
        description: '画像を開いて内容を確認してください。',
    };

    return (
        <article className="rounded-xl border border-amber-200 bg-white p-4 shadow-sm dark:border-amber-800/70 dark:bg-gray-900">
            <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                    <h3 className="font-semibold text-gray-900 dark:text-gray-100">{copy.label}</h3>
                    <p className="mt-1 break-words text-sm text-gray-600 dark:text-gray-300">
                        {warning.title}
                    </p>
                    <p className="mt-1 font-mono text-xs text-gray-400">{warning.asin}</p>
                </div>
                <span className="rounded-full bg-amber-100 px-2.5 py-1 text-xs font-medium text-amber-800 dark:bg-amber-900/40 dark:text-amber-200">
                    {warning.finding_count.toLocaleString()} 件
                </span>
            </div>

            <p className="mt-3 text-sm text-gray-600 dark:text-gray-300">{copy.description}</p>
            <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                {warning.source === 'comic' ? '漫画' : '小説'}・登録日時{' '}
                {formatDateTimeJa(warning.created_at)}
            </p>

            <div className="mt-4 flex flex-wrap items-end gap-2">
                <label className="grid gap-1 text-xs text-gray-600 dark:text-gray-300">
                    候補ページ（{warning.pages.length.toLocaleString()}ページ）
                    <select
                        value={selectedPage}
                        onChange={(event) => setSelectedPage(Number(event.target.value))}
                        className="min-h-9 rounded-md border border-gray-300 bg-white px-2 text-sm text-gray-900 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
                    >
                        {warning.pages.map((page) => (
                            <option key={page} value={page}>
                                {page} ページ
                            </option>
                        ))}
                    </select>
                </label>
                <Link
                    to={readerPath(warning, selectedPage)}
                    target="_blank"
                    rel="noreferrer"
                    className={cn(buttonVariants({ variant: 'secondary', size: 'md' }), 'min-h-9')}
                    aria-label={`${warning.title}の${selectedPage}ページを開く`}
                >
                    <ExternalLink className="h-4 w-4" />
                    ページを開く
                </Link>
                <Button
                    variant={warning.is_read ? 'secondary' : 'default'}
                    className="min-h-9"
                    disabled={updating}
                    onClick={() => onUpdateRead(warning)}
                >
                    {updating && <Loader2 className="h-4 w-4 animate-spin" />}
                    {warning.is_read ? '未確認に戻す' : '確認済みにする'}
                </Button>
            </div>
        </article>
    );
}

export function KindleCaptureQualityWarnings() {
    const [status, setStatus] = useState<KindleCaptureWarningStatus>('unread');
    const quality = useKindleCaptureQualityWarnings(status);

    const updateRead = async (warning: KindleCaptureQualityWarning) => {
        try {
            await quality.updateRead({
                warningId: warning.id,
                isRead: !warning.is_read,
            });
            toast.success(warning.is_read ? '未確認に戻しました' : '確認済みにしました');
        } catch (error) {
            toast.error(errorMessage(error, '確認状態を更新できませんでした'));
        }
    };

    const countFor = (value: KindleCaptureWarningStatus) => {
        if (value === 'unread') return quality.unreadCount;
        if (value === 'read') return quality.readCount;
        return quality.unreadCount + quality.readCount;
    };

    return (
        <section className="mt-6" aria-labelledby="capture-quality-warning-title">
            <div className="flex flex-wrap items-end justify-between gap-3">
                <div>
                    <div className="flex items-center gap-2 text-amber-700 dark:text-amber-300">
                        <AlertTriangle className="h-5 w-5" />
                        <h2 id="capture-quality-warning-title" className="text-lg font-semibold">
                            画像品質の要確認候補
                        </h2>
                    </div>
                    <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                        登録は完了しています。候補画像を目視し、確認状態を管理できます。
                    </p>
                </div>
                <div className="flex flex-wrap gap-1" role="group" aria-label="候補の確認状態">
                    {FILTERS.map((filter) => (
                        <Button
                            key={filter.value}
                            variant="secondary"
                            size="sm"
                            active={status === filter.value}
                            aria-pressed={status === filter.value}
                            onClick={() => setStatus(filter.value)}
                        >
                            {filter.label} {countFor(filter.value)}
                        </Button>
                    ))}
                </div>
            </div>

            <Alert variant="warning" className="mt-3">
                章扉、表紙、挿絵、奥付など正常なページも含まれます。この候補は登録結果、OCR開始、
                画像削除には影響しません。ページを開くだけでは確認済みになりません。
            </Alert>

            {quality.error ? (
                <Alert variant="error" className="mt-3">
                    {errorMessage(quality.error, '要確認候補を取得できませんでした')}
                </Alert>
            ) : quality.isLoading ? (
                <div className="mt-3 flex items-center justify-center gap-2 rounded-xl border border-gray-200 bg-white py-10 text-sm text-gray-500 dark:border-gray-700 dark:bg-gray-900">
                    <Loader2 className="h-5 w-5 animate-spin" />
                    要確認候補を読み込み中
                </div>
            ) : quality.warnings.length === 0 ? (
                <div className="mt-3 rounded-xl border border-dashed border-gray-300 bg-white py-10 text-center text-sm text-gray-500 dark:border-gray-700 dark:bg-gray-900">
                    {status === 'unread'
                        ? '未確認の候補はありません。'
                        : status === 'read'
                          ? '確認済みの候補はありません。'
                          : '現在の登録画像に要確認候補はありません。'}
                </div>
            ) : (
                <div className="mt-3 grid gap-3 xl:grid-cols-2">
                    {quality.warnings.map((warning) => (
                        <WarningCard
                            key={warning.id}
                            warning={warning}
                            updating={quality.updatingWarningId === warning.id}
                            onUpdateRead={(item) => void updateRead(item)}
                        />
                    ))}
                </div>
            )}
        </section>
    );
}
