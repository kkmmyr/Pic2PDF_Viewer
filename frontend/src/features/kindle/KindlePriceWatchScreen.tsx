import { type FormEvent, useState } from 'react';
import { BellRing, ChevronDown, ExternalLink, History, Loader2, Power, Trash2 } from 'lucide-react';
import { toast } from 'sonner';

import { KindlePageShell } from '@/components/kindle/KindlePageShell';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import { useKindlePriceHistory, useKindlePriceWatches } from '@/features/kindle/queries';
import type { KindlePriceWatch } from '@/features/kindle/types';
import { formatDateTimeJa } from '@/utils/date';
import { errorMessage } from '@/utils/error';

const STATUS_LABELS: Record<KindlePriceWatch['last_status'], string> = {
    never: '未確認',
    ok: '確認済み',
    partial: '一部のみ確認',
    failed: '確認失敗',
};

function formatYen(value: number | null): string {
    return value === null ? '—' : `￥${value.toLocaleString('ja-JP')}`;
}

function statusClass(status: KindlePriceWatch['last_status']): string {
    if (status === 'ok')
        return 'bg-green-50 text-green-700 dark:bg-green-900/30 dark:text-green-300';
    if (status === 'failed') return 'bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-300';
    if (status === 'partial')
        return 'bg-amber-50 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300';
    return 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300';
}

function PriceWatchCard({
    watch,
    onToggle,
    onDelete,
    updating,
}: {
    watch: KindlePriceWatch;
    onToggle: (watch: KindlePriceWatch) => void;
    onDelete: (watch: KindlePriceWatch) => void;
    updating: boolean;
}) {
    const [historyOpen, setHistoryOpen] = useState(false);
    const history = useKindlePriceHistory(watch.id, historyOpen);
    const ratio =
        watch.last_ratio_percent === null ? '—' : `${watch.last_ratio_percent.toFixed(1)}%`;

    return (
        <article className="rounded-xl border border-gray-200 bg-white p-5 dark:border-gray-700 dark:bg-gray-900">
            <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                    <h3 className="truncate text-base font-semibold text-gray-900 dark:text-gray-100">
                        {watch.title || watch.asin || 'Kindle 本'}
                    </h3>
                    <a
                        href={watch.url}
                        target="_blank"
                        rel="noreferrer"
                        className="mt-1 inline-flex max-w-full items-center gap-1 truncate text-xs text-primary-700 hover:underline dark:text-primary-300"
                    >
                        <span className="truncate">{watch.url}</span>
                        <ExternalLink className="h-3.5 w-3.5 shrink-0" />
                    </a>
                </div>
                <span
                    className={`rounded-full px-2.5 py-1 text-xs font-medium ${statusClass(watch.last_status)}`}
                >
                    {watch.enabled ? STATUS_LABELS[watch.last_status] : '停止中'}
                </span>
            </div>

            <dl className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
                <div>
                    <dt className="text-xs text-gray-500 dark:text-gray-400">現在価格</dt>
                    <dd className="mt-1 font-semibold">{formatYen(watch.last_current_price)}</dd>
                </div>
                <div>
                    <dt className="text-xs text-gray-500 dark:text-gray-400">定価/参考価格</dt>
                    <dd className="mt-1 font-semibold">{formatYen(watch.last_list_price)}</dd>
                </div>
                <div>
                    <dt className="text-xs text-gray-500 dark:text-gray-400">定価比</dt>
                    <dd className="mt-1 font-semibold">{ratio}</dd>
                </div>
                <div>
                    <dt className="text-xs text-gray-500 dark:text-gray-400">通知条件</dt>
                    <dd className="mt-1 font-semibold">{watch.threshold_percent}%未満</dd>
                </div>
            </dl>

            <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-gray-100 pt-3 text-xs text-gray-500 dark:border-gray-800 dark:text-gray-400">
                <div>
                    {watch.last_checked_at
                        ? `最終確認: ${formatDateTimeJa(watch.last_checked_at)}`
                        : 'Codexブラウザによる確認はまだありません'}
                    {watch.last_error && (
                        <p className="mt-1 text-red-600 dark:text-red-400">{watch.last_error}</p>
                    )}
                </div>
                <div className="flex gap-2">
                    <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setHistoryOpen((open) => !open)}
                        aria-expanded={historyOpen}
                        aria-controls={`kindle-price-history-${watch.id}`}
                    >
                        <History className="h-4 w-4" />
                        履歴
                        <ChevronDown
                            className={`h-4 w-4 transition-transform ${historyOpen ? 'rotate-180' : ''}`}
                        />
                    </Button>
                    <Button
                        variant="secondary"
                        size="sm"
                        disabled={updating}
                        onClick={() => onToggle(watch)}
                        aria-label={`${watch.title || watch.asin || '価格監視'}を${watch.enabled ? '停止' : '再開'}`}
                    >
                        {updating ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                            <Power className="h-4 w-4" />
                        )}
                        {watch.enabled ? '停止' : '再開'}
                    </Button>
                    <Button
                        variant="destructive"
                        size="sm"
                        onClick={() => onDelete(watch)}
                        aria-label={`${watch.title || watch.asin || '価格監視'}を削除`}
                    >
                        <Trash2 className="h-4 w-4" />
                        削除
                    </Button>
                </div>
            </div>

            {historyOpen && (
                <div
                    id={`kindle-price-history-${watch.id}`}
                    className="mt-4 border-t border-gray-100 pt-3 dark:border-gray-800"
                >
                    <h4 className="text-sm font-semibold">価格履歴</h4>
                    {history.isLoading ? (
                        <div className="mt-3 flex items-center gap-2 text-xs text-gray-500">
                            <Loader2 className="h-4 w-4 animate-spin" />
                            履歴を読み込み中
                        </div>
                    ) : history.error ? (
                        <p className="mt-3 text-xs text-red-600 dark:text-red-400">
                            {errorMessage(history.error, '価格履歴を取得できませんでした')}
                        </p>
                    ) : history.data?.items.length === 0 ? (
                        <p className="mt-3 text-xs text-gray-500">価格履歴はありません。</p>
                    ) : (
                        <div className="mt-3 overflow-x-auto">
                            <table className="w-full min-w-[34rem] text-left text-xs">
                                <thead className="border-b border-gray-200 text-gray-500 dark:border-gray-700 dark:text-gray-400">
                                    <tr>
                                        <th className="px-2 py-2 font-medium">確認日時</th>
                                        <th className="px-2 py-2 font-medium">現在価格</th>
                                        <th className="px-2 py-2 font-medium">定価/参考価格</th>
                                        <th className="px-2 py-2 font-medium">定価比</th>
                                        <th className="px-2 py-2 font-medium">状態</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {history.data?.items.map((item) => (
                                        <tr
                                            key={item.id}
                                            className="border-b border-gray-100 last:border-0 dark:border-gray-800"
                                        >
                                            <td className="whitespace-nowrap px-2 py-2">
                                                {formatDateTimeJa(item.observed_at)}
                                            </td>
                                            <td className="px-2 py-2">
                                                {formatYen(item.current_price)}
                                            </td>
                                            <td className="px-2 py-2">
                                                {formatYen(item.list_price)}
                                            </td>
                                            <td className="px-2 py-2">
                                                {item.ratio_percent === null
                                                    ? '—'
                                                    : `${item.ratio_percent.toFixed(1)}%`}
                                            </td>
                                            <td className="px-2 py-2">
                                                {item.status === 'ok'
                                                    ? '確認済み'
                                                    : item.status === 'partial'
                                                      ? '一部のみ'
                                                      : item.error_message || '確認失敗'}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </div>
            )}
        </article>
    );
}

export function KindlePriceWatchScreen() {
    const watches = useKindlePriceWatches();
    const [url, setUrl] = useState('');
    const [title, setTitle] = useState('');
    const [threshold, setThreshold] = useState('50');
    const [notifyOnDrop, setNotifyOnDrop] = useState(true);
    const [notifyBelowThreshold, setNotifyBelowThreshold] = useState(true);
    const [deleteTarget, setDeleteTarget] = useState<KindlePriceWatch | null>(null);
    const [updatingId, setUpdatingId] = useState<number | null>(null);

    const submit = async (event: FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        const thresholdValue = Number(threshold);
        if (!Number.isFinite(thresholdValue) || thresholdValue < 1 || thresholdValue > 100) {
            toast.error('定価比は1〜100の範囲で入力してください');
            return;
        }
        try {
            await watches.create({
                url: url.trim(),
                title: title.trim() || null,
                threshold_percent: thresholdValue,
                notify_on_drop: notifyOnDrop,
                notify_below_threshold: notifyBelowThreshold,
                enabled: true,
            });
            setUrl('');
            setTitle('');
            toast.success('価格監視を追加しました');
        } catch (error) {
            toast.error(errorMessage(error, '価格監視の追加に失敗しました'));
        }
    };

    const toggle = async (watch: KindlePriceWatch) => {
        setUpdatingId(watch.id);
        try {
            await watches.update({ watchId: watch.id, request: { enabled: !watch.enabled } });
            toast.success(watch.enabled ? '価格監視を停止しました' : '価格監視を再開しました');
        } catch (error) {
            toast.error(errorMessage(error, '価格監視の状態変更に失敗しました'));
        } finally {
            setUpdatingId(null);
        }
    };

    const remove = async () => {
        if (!deleteTarget) return;
        try {
            await watches.remove(deleteTarget.id);
            toast.success('価格監視を削除しました');
        } catch (error) {
            toast.error(errorMessage(error, '価格監視の削除に失敗しました'));
        } finally {
            setDeleteTarget(null);
        }
    };

    return (
        <KindlePageShell
            title="Kindle 価格監視"
            description="Amazonの商品ページをCodexのブラウザで確認し、設定した定価比を下回ったら通知します"
        >
            <Alert variant="info" className="mb-4">
                <p>
                    Kinseli
                    APIやサーバーからのAmazon直接取得は使いません。スケジュール実行時にCodexが各URLを開き、ページに表示されたKindle版の現在価格と定価/参考価格だけを読み取ります。ログイン画面・CAPTCHA・価格不明の場合は通知せず、確認失敗として記録します。
                </p>
                <p className="mt-1">
                    Discord通知を使う場合は、サーバーの環境変数
                    <code className="mx-1 rounded bg-black/10 px-1">
                        KINDLE_PRICE_DISCORD_WEBHOOK_URL
                    </code>
                    を設定してください。
                </p>
            </Alert>

            <section className="rounded-xl border border-gray-200 bg-white p-5 dark:border-gray-700 dark:bg-gray-900">
                <div className="flex items-center gap-2">
                    <BellRing className="h-5 w-5 text-primary-600 dark:text-primary-300" />
                    <h2 className="text-lg font-semibold">監視する本を追加</h2>
                </div>
                <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                    Amazon.co.jp のKindle商品ページURL（/dp/BXXXXXXXXX）を登録してください。
                </p>
                <form className="mt-4 grid gap-4" onSubmit={(event) => void submit(event)}>
                    <div>
                        <label htmlFor="kindle-price-watch-url" className="text-sm font-medium">
                            Amazon商品URL <span className="text-red-600">*</span>
                        </label>
                        <input
                            id="kindle-price-watch-url"
                            type="url"
                            required
                            value={url}
                            onChange={(event) => setUrl(event.target.value)}
                            placeholder="https://www.amazon.co.jp/dp/BXXXXXXXXX"
                            className="mt-1 min-h-11 w-full rounded-lg border border-gray-300 bg-white px-3 text-sm outline-none focus:border-primary-500 focus:ring-2 focus:ring-primary-500/30 dark:border-gray-600 dark:bg-gray-800"
                        />
                    </div>
                    <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_12rem]">
                        <div>
                            <label
                                htmlFor="kindle-price-watch-title"
                                className="text-sm font-medium"
                            >
                                表示名（任意）
                            </label>
                            <input
                                id="kindle-price-watch-title"
                                type="text"
                                value={title}
                                onChange={(event) => setTitle(event.target.value)}
                                placeholder="本のタイトル"
                                className="mt-1 min-h-11 w-full rounded-lg border border-gray-300 bg-white px-3 text-sm outline-none focus:border-primary-500 focus:ring-2 focus:ring-primary-500/30 dark:border-gray-600 dark:bg-gray-800"
                            />
                        </div>
                        <div>
                            <label
                                htmlFor="kindle-price-watch-threshold"
                                className="text-sm font-medium"
                            >
                                通知する定価比（%）
                            </label>
                            <input
                                id="kindle-price-watch-threshold"
                                type="number"
                                min="1"
                                max="100"
                                step="1"
                                value={threshold}
                                onChange={(event) => setThreshold(event.target.value)}
                                className="mt-1 min-h-11 w-full rounded-lg border border-gray-300 bg-white px-3 text-sm outline-none focus:border-primary-500 focus:ring-2 focus:ring-primary-500/30 dark:border-gray-600 dark:bg-gray-800"
                            />
                        </div>
                    </div>
                    <div className="flex flex-wrap gap-x-6 gap-y-3 text-sm">
                        <label className="inline-flex min-h-11 items-center gap-2">
                            <input
                                type="checkbox"
                                checked={notifyBelowThreshold}
                                onChange={(event) => setNotifyBelowThreshold(event.target.checked)}
                                className="h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                            />
                            定価比を下回ったら通知
                        </label>
                        <label className="inline-flex min-h-11 items-center gap-2">
                            <input
                                type="checkbox"
                                checked={notifyOnDrop}
                                onChange={(event) => setNotifyOnDrop(event.target.checked)}
                                className="h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                            />
                            前回より値下がりしたら通知
                        </label>
                    </div>
                    <div>
                        <Button
                            type="submit"
                            disabled={watches.creating || !url.trim()}
                            className="min-h-11"
                        >
                            {watches.creating && <Loader2 className="h-4 w-4 animate-spin" />}
                            監視対象を追加
                        </Button>
                    </div>
                </form>
            </section>

            {watches.error && (
                <Alert variant="error" className="mt-4">
                    {errorMessage(watches.error, '価格監視一覧を取得できませんでした')}
                </Alert>
            )}

            <section className="mt-4">
                <div className="mb-3 flex items-baseline justify-between gap-3">
                    <h2 className="text-lg font-semibold">監視対象一覧</h2>
                    <span className="text-sm text-gray-500 dark:text-gray-400">
                        {watches.watches.length}件
                    </span>
                </div>
                {watches.isLoading ? (
                    <div className="flex items-center gap-2 rounded-xl border border-gray-200 bg-white p-8 text-sm text-gray-500 dark:border-gray-700 dark:bg-gray-900">
                        <Loader2 className="h-4 w-4 animate-spin" />
                        監視対象を読み込み中
                    </div>
                ) : watches.watches.length === 0 ? (
                    <div className="rounded-xl border border-dashed border-gray-300 bg-white p-8 text-center text-sm text-gray-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-400">
                        監視対象はまだありません。
                    </div>
                ) : (
                    <div className="grid gap-4">
                        {watches.watches.map((watch) => (
                            <PriceWatchCard
                                key={watch.id}
                                watch={watch}
                                onToggle={(target) => void toggle(target)}
                                onDelete={setDeleteTarget}
                                updating={updatingId === watch.id || watches.updating}
                            />
                        ))}
                    </div>
                )}
            </section>

            <ConfirmDialog
                open={deleteTarget !== null}
                title="価格監視を削除しますか？"
                message={`${deleteTarget?.title || deleteTarget?.asin || 'この本'}の履歴も削除されます。この操作は取り消せません。`}
                confirmLabel="削除"
                danger
                confirmDisabled={watches.removing}
                onConfirm={() => void remove()}
                onCancel={() => setDeleteTarget(null)}
            />
        </KindlePageShell>
    );
}
