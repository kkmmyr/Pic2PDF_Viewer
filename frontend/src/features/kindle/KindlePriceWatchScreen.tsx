import { type FormEvent, useState } from 'react';
import { BellRing, Loader2 } from 'lucide-react';
import { toast } from 'sonner';

import { KindlePageShell } from '@/components/kindle/KindlePageShell';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import { PriceWatchCard } from '@/features/kindle/PriceWatchCard';
import { useKindlePriceWatches } from '@/features/kindle/queries';
import type { KindlePriceWatch } from '@/features/kindle/types';
import { errorMessage } from '@/utils/error';

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
            description="Amazonの商品ページをCodexのブラウザで確認し、ポイント差引後の実質価格で通知します"
        >
            <Alert variant="info" className="mb-4">
                <p>
                    Kinseli
                    APIやサーバーからのAmazon直接取得は使いません。スケジュール実行時にCodexが各URLを開き、Kindle版の現在価格・付与ポイント・定価/参考価格を読み取ります。Kindle定価がない場合は同じ商品ページの紙版定価を使い、ポイント差引後の実質価格で判定します。ログイン画面・CAPTCHA・価格不明の場合は通知せず、確認失敗として記録します。
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
