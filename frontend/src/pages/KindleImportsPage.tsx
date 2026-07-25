import { useState } from 'react';
import { Database, Download, Loader2, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';

import { KindlePageShell } from '@/components/kindle/KindlePageShell';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import { useKindleImports } from '@/hooks/useKindleCatalog';
import type { KindleMigrationPreview, KindleOrdersImport } from '@/types/kindleCatalog';
import { formatDateTimeJa } from '@/utils/date';
import { errorMessage } from '@/utils/error';

type ImportKind = 'kindle-info' | 'orders' | 'autobuy';
type ImportStatus = 'idle' | 'running' | 'success' | 'unchanged' | 'error';

interface ImportDisplayState {
    status: ImportStatus;
    message: string;
}

const IMPORT_LABELS: Record<ImportKind, string> = {
    'kindle-info': 'Kindle Info',
    orders: 'Amazon CSV',
    autobuy: 'シリーズ自動購入',
};

const IMPORT_ORDER: ImportKind[] = ['kindle-info', 'orders', 'autobuy'];
const IMPORT_RUN_LABELS: Record<string, string> = {
    kindle_info: 'Kindle Info',
    amazon_orders: 'Amazon CSV',
    autobuy: 'シリーズ自動購入',
    legacy_db: '旧DB移行',
};
const IMPORT_RUN_STATUS_LABELS: Record<string, string> = {
    running: '実行中',
    succeeded: '完了',
    failed: '失敗',
};

function resultState(result: KindleOrdersImport): ImportDisplayState {
    if (result.records_processed === 0 && result.files_skipped > 0) {
        return {
            status: 'unchanged',
            message: `${result.files_skipped} ファイル変更なし`,
        };
    }
    return {
        status: 'success',
        message: `${result.records_processed.toLocaleString()} 件更新`,
    };
}

function ImportStatusText({ state }: { state: ImportDisplayState }) {
    const color =
        state.status === 'error'
            ? 'text-red-600 dark:text-red-400'
            : state.status === 'success'
              ? 'text-green-600 dark:text-green-400'
              : state.status === 'running'
                ? 'text-primary-600 dark:text-primary-300'
                : 'text-gray-500 dark:text-gray-400';
    return <div className={`mt-2 text-xs ${color}`}>{state.message || '未実行'}</div>;
}

export default function KindleImportsPage() {
    const imports = useKindleImports();
    const [preview, setPreview] = useState<KindleMigrationPreview | null>(null);
    const [runningAll, setRunningAll] = useState(false);
    const [states, setStates] = useState<Record<ImportKind, ImportDisplayState>>({
        'kindle-info': { status: 'idle', message: '' },
        orders: { status: 'idle', message: '' },
        autobuy: { status: 'idle', message: '' },
    });

    const runImport = async (kind: ImportKind) => {
        setStates((current) => ({
            ...current,
            [kind]: { status: 'running', message: '実行中…' },
        }));
        try {
            const result =
                kind === 'kindle-info'
                    ? await imports.importKindleInfo()
                    : kind === 'orders'
                      ? await imports.importOrders()
                      : await imports.importAutobuy();
            setStates((current) => ({ ...current, [kind]: resultState(result) }));
            return true;
        } catch (error) {
            const message = errorMessage(error, `${IMPORT_LABELS[kind]} の取り込みに失敗しました`);
            setStates((current) => ({
                ...current,
                [kind]: { status: 'error', message },
            }));
            return false;
        }
    };

    const runAll = async () => {
        setRunningAll(true);
        let failed = 0;
        for (const kind of IMPORT_ORDER) {
            if (!(await runImport(kind))) failed += 1;
        }
        setRunningAll(false);
        if (failed === 0) toast.success('すべての差分取込が完了しました');
        else toast.error(`${failed} 件の取込処理が失敗しました`);
    };

    const handlePreview = async () => {
        try {
            setPreview(await imports.preview());
        } catch (error) {
            toast.error(errorMessage(error, '移行プレビューに失敗しました'));
        }
    };

    const handleCommit = async () => {
        if (!preview) return;
        try {
            const result = await imports.commit(preview.confirmation_token);
            toast.success(`${result.records_processed.toLocaleString()} 件を移行しました`);
            setPreview(null);
        } catch (error) {
            toast.error(errorMessage(error, '移行に失敗しました'));
        }
    };

    const isImporting =
        runningAll ||
        imports.importingKindleInfo ||
        imports.importingOrders ||
        imports.importingAutobuy;
    const importConfigured = imports.sources?.amazon_data_configured ?? false;

    return (
        <KindlePageShell
            title="取込・管理"
            description="月次の差分取込と初回移行などの低頻度操作を管理します"
            actions={
                <Button
                    onClick={() => void runAll()}
                    disabled={!importConfigured || isImporting}
                    className="min-h-10"
                >
                    {runningAll ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                        <RefreshCw className="h-4 w-4" />
                    )}
                    すべて差分取込
                </Button>
            }
        >
            {!importConfigured && !imports.loading && (
                <Alert variant="warning" className="mb-4">
                    Amazonデータの入力元が設定されていません。サーバーのAMAZON_DATA_DIRを確認してください。
                </Alert>
            )}
            {imports.error && (
                <Alert variant="error" className="mb-4">
                    {errorMessage(imports.error, '取込状態を取得できませんでした')}
                </Alert>
            )}

            <section className="rounded-xl border border-gray-200 bg-white p-5 dark:border-gray-700 dark:bg-gray-900">
                <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                        <h2 className="text-lg font-semibold">月次差分取込</h2>
                        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                            すべて差分取込は、次の3処理を順番に実行します。
                        </p>
                    </div>
                    {imports.stats?.last_import && (
                        <div className="text-right text-xs text-gray-500 dark:text-gray-400">
                            <div>最終取込</div>
                            <div className="mt-1 font-medium text-gray-700 dark:text-gray-300">
                                {formatDateTimeJa(imports.stats.last_import.started_at)}
                            </div>
                        </div>
                    )}
                </div>

                <div className="mt-4 grid gap-3 md:grid-cols-3">
                    {IMPORT_ORDER.map((kind) => (
                        <article
                            key={kind}
                            className="rounded-lg border border-gray-200 p-4 dark:border-gray-700"
                        >
                            <div className="flex items-center gap-2 font-medium">
                                <Download className="h-4 w-4" />
                                {IMPORT_LABELS[kind]}
                            </div>
                            <ImportStatusText state={states[kind]} />
                            <Button
                                variant="secondary"
                                className="mt-4 w-full"
                                disabled={!importConfigured || isImporting}
                                onClick={() => void runImport(kind)}
                            >
                                {states[kind].status === 'running' && (
                                    <Loader2 className="h-4 w-4 animate-spin" />
                                )}
                                個別に実行
                            </Button>
                        </article>
                    ))}
                </div>
            </section>

            <section className="mt-4 rounded-xl border border-gray-200 bg-white p-5 dark:border-gray-700 dark:bg-gray-900">
                <h2 className="text-lg font-semibold">直近の取込履歴</h2>
                {imports.loading ? (
                    <div className="flex items-center gap-2 py-8 text-sm text-gray-500">
                        <Loader2 className="h-4 w-4 animate-spin" />
                        履歴を読み込み中
                    </div>
                ) : imports.runs.length === 0 ? (
                    <div className="py-8 text-sm text-gray-500">取込履歴はありません。</div>
                ) : (
                    <div className="mt-3 divide-y divide-gray-100 dark:divide-gray-800">
                        {imports.runs.map((run) => (
                            <div
                                key={run.id}
                                className="flex flex-wrap items-center justify-between gap-2 py-3 text-sm"
                            >
                                <div>
                                    <div className="font-medium">
                                        {IMPORT_RUN_LABELS[run.source_kind] ?? run.source_kind}
                                    </div>
                                    <div className="mt-1 text-xs text-gray-500">
                                        {formatDateTimeJa(run.started_at)} /{' '}
                                        {run.records_processed.toLocaleString()} 件
                                    </div>
                                </div>
                                <span className="rounded-full bg-gray-100 px-2 py-1 text-xs dark:bg-gray-800">
                                    {IMPORT_RUN_STATUS_LABELS[run.status] ?? run.status}
                                </span>
                                {run.error_message && (
                                    <div className="w-full text-xs text-red-600 dark:text-red-400">
                                        {run.error_message}
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>
                )}
            </section>

            <section className="mt-4 rounded-xl border border-amber-200 bg-amber-50/50 p-5 dark:border-amber-900 dark:bg-amber-950/20">
                <div className="flex items-center gap-2">
                    <Database className="h-5 w-5" />
                    <h2 className="text-lg font-semibold">初回移行・メンテナンス</h2>
                </div>
                <p className="mt-2 text-sm text-gray-600 dark:text-gray-300">
                    初回移行は完了済みです。再実行が必要な場合だけ、移行元と件数を確認して実行してください。
                </p>
                {!imports.sources?.legacy_db_configured && !imports.loading && (
                    <Alert variant="warning" className="mt-3">
                        KINDLE_LEGACY_DB_PATHが設定されていません。
                    </Alert>
                )}
                <Button
                    variant="secondary"
                    className="mt-4"
                    disabled={
                        !imports.sources?.legacy_db_available ||
                        imports.previewing ||
                        imports.committing
                    }
                    onClick={() => void handlePreview()}
                >
                    {imports.previewing ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                        <Database className="h-4 w-4" />
                    )}
                    旧DB移行内容を確認
                </Button>
            </section>

            <ConfirmDialog
                open={preview !== null}
                title="旧Kindleカタログを移行"
                message={
                    preview
                        ? [
                              `書籍: ${(preview.counts.books ?? 0).toLocaleString()} 件`,
                              `購入履歴: ${(preview.counts.purchases ?? 0).toLocaleString()} 件`,
                              `レビュー除外: ${(preview.excluded_counts.book_reviews ?? 0).toLocaleString()} 件`,
                              '',
                              '旧アプリの画像・表紙キャッシュ・レビューは移行しません。',
                              'Pic2PDFViewerの既存画像には影響しません。',
                          ].join('\n')
                        : ''
                }
                confirmLabel={imports.committing ? '移行中…' : 'カタログを移行'}
                confirmDisabled={imports.committing}
                onConfirm={() => void handleCommit()}
                onCancel={() => {
                    if (!imports.committing) setPreview(null);
                }}
            />
        </KindlePageShell>
    );
}
