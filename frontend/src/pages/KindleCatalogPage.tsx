import { useState } from 'react';
import {
    BookCopy,
    ChevronLeft,
    ChevronRight,
    Database,
    Download,
    Link2,
    Loader2,
    Search,
    ScanLine,
} from 'lucide-react';
import { toast } from 'sonner';

import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import { useKindleCatalog, useKindleLinkCandidates } from '@/hooks/useKindleCatalog';
import type {
    KindleCatalogBook,
    KindleCatalogFilters,
    KindleMigrationPreview,
} from '@/types/kindleCatalog';
import { errorMessage } from '@/utils/error';

const PAGE_SIZE = 50;

const OWNERSHIP_LABELS: Record<KindleCatalogBook['ownership'], string> = {
    purchased: '購入',
    borrowed_active: 'KU借用中',
    borrowed_ended: 'KU終了',
    returned: '返品',
    unknown: '不明',
};

const CAPTURE_LABELS: Record<KindleCatalogBook['capture_state'], string> = {
    not_captured: '画像なし',
    captured: '取込済み',
    multiple_links: '重複確認',
    capture_pending: '取込中',
};

function StatCard({ label, value }: { label: string; value: number | undefined }) {
    return (
        <div className="rounded-xl border border-gray-200 bg-white px-4 py-3 dark:border-gray-700 dark:bg-gray-900">
            <div className="text-xs text-gray-500 dark:text-gray-400">{label}</div>
            <div className="mt-1 text-2xl font-semibold tabular-nums">{value ?? '—'}</div>
        </div>
    );
}

function BookRow({
    book,
    creatingCaptureJob,
    onCreateCaptureJob,
}: {
    book: KindleCatalogBook;
    creatingCaptureJob: boolean;
    onCreateCaptureJob: (book: KindleCatalogBook, source: 'comic' | 'novel') => void;
}) {
    return (
        <tr className="border-b border-gray-100 align-top last:border-0 dark:border-gray-800">
            <td className="px-4 py-3">
                <div className="font-medium text-gray-900 dark:text-gray-100">{book.title}</div>
                <div className="mt-1 font-mono text-xs text-gray-400">{book.asin}</div>
            </td>
            <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-300">
                {book.authors.join(' / ') || '—'}
            </td>
            <td className="px-4 py-3 text-sm">
                <div>{book.series_name ?? '—'}</div>
                {book.volume_label && (
                    <div className="text-xs text-gray-500">巻: {book.volume_label}</div>
                )}
            </td>
            <td className="px-4 py-3">
                <span className="rounded-full bg-blue-50 px-2 py-1 text-xs text-blue-700 dark:bg-blue-950 dark:text-blue-300">
                    {OWNERSHIP_LABELS[book.ownership]}
                </span>
            </td>
            <td className="px-4 py-3">
                <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded-full bg-gray-100 px-2 py-1 text-xs text-gray-700 dark:bg-gray-800 dark:text-gray-300">
                        {CAPTURE_LABELS[book.capture_state]}
                    </span>
                    {book.capture_state === 'not_captured' && (
                        <>
                            <button
                                type="button"
                                disabled={creatingCaptureJob}
                                onClick={() => onCreateCaptureJob(book, 'comic')}
                                className="text-xs font-medium text-primary-700 hover:underline disabled:opacity-50 dark:text-primary-300"
                            >
                                漫画撮影
                            </button>
                            <button
                                type="button"
                                disabled={creatingCaptureJob}
                                onClick={() => onCreateCaptureJob(book, 'novel')}
                                className="text-xs font-medium text-primary-700 hover:underline disabled:opacity-50 dark:text-primary-300"
                            >
                                小説撮影
                            </button>
                        </>
                    )}
                </div>
            </td>
        </tr>
    );
}

export default function KindleCatalogPage() {
    const [filters, setFilters] = useState<KindleCatalogFilters>({
        q: '',
        bookType: '',
        ownership: '',
        captureState: '',
        page: 1,
        pageSize: PAGE_SIZE,
    });
    const [preview, setPreview] = useState<KindleMigrationPreview | null>(null);
    const [selectedLinkKey, setSelectedLinkKey] = useState('');
    const catalog = useKindleCatalog(filters);
    const selectedUnlinked =
        catalog.unlinked.find((book) => `${book.source}:${book.book_id}` === selectedLinkKey) ??
        null;
    const linkCandidates = useKindleLinkCandidates(
        selectedUnlinked?.source ?? null,
        selectedUnlinked?.book_id ?? null,
    );

    const updateFilter = <K extends Exclude<keyof KindleCatalogFilters, 'page' | 'pageSize'>>(
        key: K,
        value: KindleCatalogFilters[K],
    ) => setFilters((current) => ({ ...current, [key]: value, page: 1 }));
    const setPage = (page: number) => setFilters((current) => ({ ...current, page }));

    const handlePreview = async () => {
        try {
            setPreview(await catalog.preview());
        } catch (error) {
            toast.error(errorMessage(error, '移行プレビューに失敗しました'));
        }
    };

    const handleCommit = async () => {
        if (!preview) return;
        try {
            const result = await catalog.commit(preview.confirmation_token);
            toast.success(`${result.records_processed.toLocaleString()} 件を移行しました`);
            setPreview(null);
        } catch (error) {
            toast.error(errorMessage(error, '移行に失敗しました'));
        }
    };

    const handleOrdersImport = async () => {
        try {
            const result = await catalog.importOrders();
            toast.success(
                `Amazon CSV: ${result.records_processed.toLocaleString()} 件取込 / ${result.files_skipped} ファイル変更なし`,
            );
        } catch (error) {
            toast.error(errorMessage(error, 'Amazon CSV の取り込みに失敗しました'));
        }
    };

    const handleKindleInfoImport = async () => {
        try {
            const result = await catalog.importKindleInfo();
            toast.success(
                `Kindle Info: ${result.records_processed.toLocaleString()} 件更新 / ${result.files_skipped} ファイル変更なし`,
            );
        } catch (error) {
            toast.error(errorMessage(error, 'Kindle Info の取り込みに失敗しました'));
        }
    };

    const handleAutobuyImport = async () => {
        try {
            const result = await catalog.importAutobuy();
            toast.success(`シリーズ自動購入: ${result.records_processed.toLocaleString()} 件取込`);
        } catch (error) {
            toast.error(errorMessage(error, 'シリーズ自動購入情報の取り込みに失敗しました'));
        }
    };

    const handleLink = async (asin: string) => {
        if (!selectedUnlinked) return;
        try {
            await catalog.link({
                source: selectedUnlinked.source,
                bookId: selectedUnlinked.book_id,
                asin,
            });
            toast.success('Pic2PDFViewer の既存画像へ ASIN を紐付けました');
            setSelectedLinkKey('');
        } catch (error) {
            toast.error(errorMessage(error, 'ASIN の紐付けに失敗しました'));
        }
    };

    const handleCreateCaptureJob = async (book: KindleCatalogBook, source: 'comic' | 'novel') => {
        try {
            await catalog.createCaptureJob({ asin: book.asin, source });
            toast.success(
                `「${book.title}」を${source === 'comic' ? '漫画' : '小説'}キャプチャ待ちに追加しました`,
            );
        } catch (error) {
            toast.error(errorMessage(error, 'キャプチャジョブの作成に失敗しました'));
        }
    };

    const totalPages = Math.max(1, Math.ceil((catalog.books?.total ?? 0) / PAGE_SIZE));

    return (
        <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
            <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
                <div>
                    <h1 className="flex items-center gap-2 text-2xl font-bold">
                        <BookCopy className="h-6 w-6" />
                        Kindle 購入書籍
                    </h1>
                    <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                        Linux サーバー管理の購入・借用カタログ
                    </p>
                </div>
                <div className="flex flex-wrap gap-2">
                    <button
                        type="button"
                        onClick={() => void handleKindleInfoImport()}
                        disabled={
                            !catalog.sources?.amazon_data_configured || catalog.importingKindleInfo
                        }
                        className="inline-flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-gray-600 dark:bg-gray-900 dark:hover:bg-gray-800"
                    >
                        {catalog.importingKindleInfo ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                            <Download className="h-4 w-4" />
                        )}
                        Kindle Info 差分取込
                    </button>
                    <button
                        type="button"
                        onClick={() => void handleAutobuyImport()}
                        disabled={
                            !catalog.sources?.amazon_data_configured || catalog.importingAutobuy
                        }
                        className="inline-flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-gray-600 dark:bg-gray-900 dark:hover:bg-gray-800"
                    >
                        {catalog.importingAutobuy ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                            <Download className="h-4 w-4" />
                        )}
                        シリーズ自動購入取込
                    </button>
                    <button
                        type="button"
                        onClick={() => void handleOrdersImport()}
                        disabled={
                            !catalog.sources?.amazon_data_configured || catalog.importingOrders
                        }
                        className="inline-flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-gray-600 dark:bg-gray-900 dark:hover:bg-gray-800"
                    >
                        {catalog.importingOrders ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                            <Download className="h-4 w-4" />
                        )}
                        Amazon CSV 差分取込
                    </button>
                    <button
                        type="button"
                        onClick={() => void handlePreview()}
                        disabled={
                            !catalog.sources?.legacy_db_available ||
                            catalog.previewing ||
                            catalog.committing
                        }
                        className="inline-flex items-center gap-2 rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                        {catalog.previewing ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                            <Database className="h-4 w-4" />
                        )}
                        旧DB移行を確認
                    </button>
                </div>
            </div>

            <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
                <StatCard label="書籍" value={catalog.stats?.books} />
                <StatCard label="購入履歴" value={catalog.stats?.purchases} />
                <StatCard label="KU借用" value={catalog.stats?.borrowings} />
                <StatCard label="返品" value={catalog.stats?.returns} />
                <StatCard label="シリーズ" value={catalog.stats?.series} />
                <StatCard label="画像紐付け" value={catalog.stats?.captured} />
            </div>

            {!catalog.sources?.legacy_db_configured && !catalog.loading && (
                <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
                    初回移行を使う場合は Linux サーバーに KINDLE_LEGACY_DB_PATH を設定してください。
                </div>
            )}

            <div className="mb-4 grid gap-3 rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-900 md:grid-cols-[minmax(260px,1fr)_180px_180px_180px]">
                <label className="relative">
                    <span className="sr-only">タイトル・ASIN・著者を検索</span>
                    <Search className="absolute left-3 top-2.5 h-4 w-4 text-gray-400" />
                    <input
                        value={filters.q}
                        onChange={(event) => updateFilter('q', event.target.value)}
                        placeholder="タイトル・ASIN・著者を検索"
                        className="w-full rounded-lg border border-gray-300 bg-white py-2 pl-9 pr-3 text-sm dark:border-gray-600 dark:bg-gray-800"
                    />
                </label>
                <select
                    aria-label="書籍種別"
                    value={filters.bookType}
                    onChange={(event) =>
                        updateFilter(
                            'bookType',
                            event.target.value as KindleCatalogFilters['bookType'],
                        )
                    }
                    className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800"
                >
                    <option value="">全種別</option>
                    <option value="comic">漫画</option>
                    <option value="novel">小説</option>
                    <option value="other">その他</option>
                    <option value="unknown">未分類</option>
                </select>
                <select
                    aria-label="所有状態"
                    value={filters.ownership}
                    onChange={(event) =>
                        updateFilter(
                            'ownership',
                            event.target.value as KindleCatalogFilters['ownership'],
                        )
                    }
                    className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800"
                >
                    <option value="">全所有状態</option>
                    <option value="purchased">購入</option>
                    <option value="borrowed_active">KU借用中</option>
                    <option value="borrowed_ended">KU終了</option>
                    <option value="returned">返品</option>
                </select>
                <select
                    aria-label="画像取込状態"
                    value={filters.captureState}
                    onChange={(event) =>
                        updateFilter(
                            'captureState',
                            event.target.value as KindleCatalogFilters['captureState'],
                        )
                    }
                    className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800"
                >
                    <option value="">全画像状態</option>
                    <option value="not_captured">画像なし</option>
                    <option value="captured">取込済み</option>
                    <option value="multiple_links">重複確認</option>
                    <option value="capture_pending">取込中</option>
                </select>
            </div>

            {catalog.error && (
                <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
                    {errorMessage(catalog.error, 'カタログを取得できませんでした')}
                </div>
            )}

            <div className="overflow-hidden rounded-xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900">
                <div className="overflow-x-auto">
                    <table className="w-full min-w-[900px]">
                        <thead className="bg-gray-50 text-left text-xs uppercase text-gray-500 dark:bg-gray-800/70 dark:text-gray-400">
                            <tr>
                                <th className="px-4 py-3">書籍</th>
                                <th className="px-4 py-3">著者</th>
                                <th className="px-4 py-3">シリーズ</th>
                                <th className="px-4 py-3">所有</th>
                                <th className="px-4 py-3">画像</th>
                            </tr>
                        </thead>
                        <tbody>
                            {catalog.books?.items.map((book) => (
                                <BookRow
                                    key={book.asin}
                                    book={book}
                                    creatingCaptureJob={catalog.creatingCaptureJob}
                                    onCreateCaptureJob={(target, source) =>
                                        void handleCreateCaptureJob(target, source)
                                    }
                                />
                            ))}
                        </tbody>
                    </table>
                </div>
                {!catalog.loading && (catalog.books?.items.length ?? 0) === 0 && (
                    <div className="flex flex-col items-center py-16 text-gray-500">
                        <Database className="mb-2 h-8 w-8" />
                        <p>該当する書籍はありません</p>
                    </div>
                )}
                <div className="flex items-center justify-between border-t border-gray-200 px-4 py-3 text-sm dark:border-gray-700">
                    <span>{(catalog.books?.total ?? 0).toLocaleString()} 件</span>
                    <div className="flex items-center gap-2">
                        <button
                            type="button"
                            aria-label="前のページ"
                            disabled={filters.page <= 1}
                            onClick={() => setPage(filters.page - 1)}
                            className="rounded p-1 hover:bg-gray-100 disabled:opacity-30 dark:hover:bg-gray-800"
                        >
                            <ChevronLeft className="h-5 w-5" />
                        </button>
                        <span>
                            {filters.page} / {totalPages}
                        </span>
                        <button
                            type="button"
                            aria-label="次のページ"
                            disabled={filters.page >= totalPages}
                            onClick={() => setPage(filters.page + 1)}
                            className="rounded p-1 hover:bg-gray-100 disabled:opacity-30 dark:hover:bg-gray-800"
                        >
                            <ChevronRight className="h-5 w-5" />
                        </button>
                    </div>
                </div>
            </div>

            <section className="mt-6 rounded-xl border border-gray-200 bg-white p-5 dark:border-gray-700 dark:bg-gray-900">
                <h2 className="flex items-center gap-2 text-lg font-semibold">
                    <ScanLine className="h-5 w-5" />
                    キャプチャジョブ
                </h2>
                <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                    Windows エージェントが上から順に取得します。
                </p>
                <div className="mt-4 space-y-2">
                    {catalog.captureJobs.slice(0, 10).map((job) => (
                        <div
                            key={job.id}
                            className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-gray-200 px-4 py-3 text-sm dark:border-gray-700"
                        >
                            <div>
                                <span className="font-medium">{job.title ?? job.asin}</span>
                                <span className="ml-2 text-xs text-gray-500">
                                    {job.source} / {job.direction}
                                </span>
                            </div>
                            <span className="rounded-full bg-gray-100 px-2 py-1 text-xs dark:bg-gray-800">
                                {job.status}
                            </span>
                        </div>
                    ))}
                    {catalog.captureJobs.length === 0 && (
                        <p className="py-3 text-sm text-gray-500">キャプチャジョブはありません。</p>
                    )}
                </div>
            </section>

            <section className="mt-6 rounded-xl border border-gray-200 bg-white p-5 dark:border-gray-700 dark:bg-gray-900">
                <div className="mb-4">
                    <h2 className="flex items-center gap-2 text-lg font-semibold">
                        <Link2 className="h-5 w-5" />
                        Pic2PDFViewer 既存画像の紐付け
                    </h2>
                    <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                        comic / novel に既にある画像だけが対象です。候補は自動確定されません。
                    </p>
                </div>
                <select
                    aria-label="未紐付け画像書籍"
                    value={selectedLinkKey}
                    onChange={(event) => setSelectedLinkKey(event.target.value)}
                    className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800"
                >
                    <option value="">未紐付け書籍を選択（{catalog.unlinked.length} 件）</option>
                    {catalog.unlinked.map((book) => (
                        <option
                            key={`${book.source}:${book.book_id}`}
                            value={`${book.source}:${book.book_id}`}
                        >
                            [{book.source}] {book.title}
                        </option>
                    ))}
                </select>

                {selectedUnlinked && (
                    <div className="mt-4 space-y-2">
                        {linkCandidates.isLoading && (
                            <div className="flex items-center gap-2 py-4 text-sm text-gray-500">
                                <Loader2 className="h-4 w-4 animate-spin" />
                                候補を検索中
                            </div>
                        )}
                        {linkCandidates.data?.items.map((candidate) => (
                            <div
                                key={candidate.asin}
                                className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-gray-200 px-4 py-3 dark:border-gray-700"
                            >
                                <div>
                                    <div className="font-medium">{candidate.title}</div>
                                    <div className="mt-1 text-xs text-gray-500">
                                        {candidate.asin} /{' '}
                                        {candidate.authors.join(' / ') || '著者不明'} / スコア{' '}
                                        {candidate.score}
                                    </div>
                                    <div className="mt-1 text-xs text-gray-400">
                                        {candidate.reasons.join('・')}
                                    </div>
                                </div>
                                <button
                                    type="button"
                                    disabled={catalog.linking}
                                    onClick={() => void handleLink(candidate.asin)}
                                    className="rounded-lg border border-primary-500 px-3 py-2 text-sm font-medium text-primary-700 hover:bg-primary-50 disabled:opacity-50 dark:text-primary-300 dark:hover:bg-primary-950"
                                >
                                    この ASIN を紐付け
                                </button>
                            </div>
                        ))}
                        {!linkCandidates.isLoading &&
                            (linkCandidates.data?.items.length ?? 0) === 0 && (
                                <p className="py-4 text-sm text-gray-500">
                                    候補がありません。カタログ検索で ASIN を確認してください。
                                </p>
                            )}
                    </div>
                )}
            </section>

            <ConfirmDialog
                open={preview !== null}
                title="旧 Kindle カタログを移行"
                message={
                    preview
                        ? [
                              `書籍: ${(preview.counts.books ?? 0).toLocaleString()} 件`,
                              `購入履歴: ${(preview.counts.purchases ?? 0).toLocaleString()} 件`,
                              `レビュー除外: ${(preview.excluded_counts.book_reviews ?? 0).toLocaleString()} 件`,
                              '',
                              '旧アプリの画像・表紙キャッシュは移行しません。',
                              'Pic2PDFViewer の既存画像には影響しません。',
                          ].join('\n')
                        : ''
                }
                confirmLabel={catalog.committing ? '移行中…' : 'カタログを移行'}
                onConfirm={() => void handleCommit()}
                onCancel={() => {
                    if (!catalog.committing) setPreview(null);
                }}
            />
        </div>
    );
}
