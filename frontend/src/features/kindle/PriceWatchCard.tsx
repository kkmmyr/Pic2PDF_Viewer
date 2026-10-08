import { useState } from 'react';
import { ChevronDown, ExternalLink, History, Loader2, Power, Trash2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { useKindlePriceHistory } from '@/features/kindle/queries';
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

function formatPoints(value: number | null): string {
    return value === null ? '—' : `${value.toLocaleString('ja-JP')} pt`;
}

function listPriceLabel(source: KindlePriceWatch['last_list_price_source']): string {
    if (source === 'paper') return '紙版定価';
    if (source === 'kindle') return 'Kindle定価/参考価格';
    return '定価/参考価格';
}

function statusClass(status: KindlePriceWatch['last_status']): string {
    if (status === 'ok')
        return 'bg-green-50 text-green-700 dark:bg-green-900/30 dark:text-green-300';
    if (status === 'failed') return 'bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-300';
    if (status === 'partial')
        return 'bg-amber-50 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300';
    return 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300';
}

export function PriceWatchCard({
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
        <article className="min-w-0 rounded-xl border border-gray-200 bg-white p-5 dark:border-gray-700 dark:bg-gray-900">
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

            <dl className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-3 lg:grid-cols-6">
                <div>
                    <dt className="text-xs text-gray-500 dark:text-gray-400">現在価格</dt>
                    <dd className="mt-1 font-semibold">{formatYen(watch.last_current_price)}</dd>
                </div>
                <div>
                    <dt className="text-xs text-gray-500 dark:text-gray-400">付与ポイント</dt>
                    <dd className="mt-1 font-semibold">{formatPoints(watch.last_points)}</dd>
                </div>
                <div>
                    <dt className="text-xs text-gray-500 dark:text-gray-400">実質価格</dt>
                    <dd className="mt-1 font-semibold">{formatYen(watch.last_effective_price)}</dd>
                </div>
                <div>
                    <dt className="text-xs text-gray-500 dark:text-gray-400">
                        {listPriceLabel(watch.last_list_price_source)}
                    </dt>
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
                            <table className="w-full min-w-[48rem] text-left text-xs">
                                <thead className="border-b border-gray-200 text-gray-500 dark:border-gray-700 dark:text-gray-400">
                                    <tr>
                                        <th className="px-2 py-2 font-medium">確認日時</th>
                                        <th className="px-2 py-2 font-medium">現在価格</th>
                                        <th className="px-2 py-2 font-medium">ポイント</th>
                                        <th className="px-2 py-2 font-medium">実質価格</th>
                                        <th className="px-2 py-2 font-medium">比較定価</th>
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
                                                {formatPoints(item.points)}
                                            </td>
                                            <td className="px-2 py-2">
                                                {formatYen(item.effective_price)}
                                            </td>
                                            <td className="px-2 py-2">
                                                <span>{formatYen(item.list_price)}</span>
                                                {item.list_price_source && (
                                                    <span className="ml-1 text-gray-500 dark:text-gray-400">
                                                        (
                                                        {item.list_price_source === 'paper'
                                                            ? '紙版'
                                                            : 'Kindle'}
                                                        )
                                                    </span>
                                                )}
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
