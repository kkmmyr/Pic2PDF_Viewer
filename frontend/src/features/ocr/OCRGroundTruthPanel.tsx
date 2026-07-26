import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Beaker, CheckCircle2, Save } from 'lucide-react';
import { toast } from 'sonner';

import { Alert } from '@/components/ui/alert';
import { API_CONFIG } from '@/config/api';
import { errorMessage } from '@/utils/error';

import { fetchOcrGroundTruth, updateOcrGroundTruth } from './api';
import type { OcrPageType } from './types';

const PAGE_TYPE_LABELS: Record<OcrPageType, string> = {
    unknown: '未分類',
    narrative: '本文',
    toc: '目次',
    illustration: '挿絵・表紙',
    colophon_or_ad: '奥付・広告',
};

export function OCRGroundTruthPanel() {
    const queryClient = useQueryClient();
    const [selectedId, setSelectedId] = useState<number | null>(null);
    const [referenceText, setReferenceText] = useState('');
    const [pageType, setPageType] = useState<OcrPageType>('unknown');
    const [note, setNote] = useState('');

    const corpusQuery = useQuery({
        queryKey: ['ocrGroundTruth'],
        queryFn: fetchOcrGroundTruth,
    });
    const corpus = corpusQuery.data;
    const selected = corpus?.entries.find((entry) => entry.id === selectedId);

    useEffect(() => {
        if (selectedId === null && corpus?.entries.length) {
            setSelectedId(corpus.entries[0].id);
        }
    }, [corpus, selectedId]);
    useEffect(() => {
        setReferenceText(selected?.reference_text ?? '');
        setPageType(selected?.page_type ?? 'unknown');
        setNote(selected?.note ?? '');
    }, [selected]);

    const mutation = useMutation({
        mutationFn: (state: 'draft' | 'verified') =>
            updateOcrGroundTruth(selectedId as number, {
                reference_text: referenceText,
                page_type: pageType,
                state,
                note: note || null,
            }),
        onSuccess: async (_, state) => {
            toast.success(
                state === 'verified' ? '正解本文を検証済みにしました' : '下書きを保存しました',
            );
            await queryClient.invalidateQueries({ queryKey: ['ocrGroundTruth'] });
        },
        onError: (error: unknown) =>
            toast.error(errorMessage(error, '正解コーパスの保存に失敗しました。')),
    });

    return (
        <section className="rounded-xl border border-gray-200 bg-white shadow-sm dark:border-gray-700 dark:bg-gray-900">
            <header className="flex flex-wrap items-center gap-3 border-b border-gray-200 px-5 py-4 dark:border-gray-700">
                <Beaker className="h-5 w-5 text-primary-600 dark:text-primary-400" />
                <div className="min-w-0 flex-1">
                    <h2 className="font-bold text-gray-900 dark:text-gray-100">OCR 正解コーパス</h2>
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                        原画像と照合して確定した本文を正解として、文字誤り率（CER）を測定します。
                    </p>
                </div>
                {corpus && (
                    <div className="text-right text-sm">
                        <div>
                            検証済み {corpus.verified_count} / {corpus.total_count}
                        </div>
                        <div className="text-gray-500">
                            CER{' '}
                            {corpus.aggregate_cer === null
                                ? '—'
                                : `${(corpus.aggregate_cer * 100).toFixed(2)}%`}
                        </div>
                    </div>
                )}
            </header>

            {corpus && corpus.metrics_by_page_type.some((metric) => metric.total_count > 0) && (
                <div
                    aria-label="ページ種別ごとのOCR品質"
                    className="grid gap-2 border-b border-gray-200 px-5 py-3 sm:grid-cols-2 xl:grid-cols-4 dark:border-gray-700"
                >
                    {corpus.metrics_by_page_type
                        .filter((metric) => metric.total_count > 0)
                        .map((metric) => (
                            <div
                                key={metric.page_type}
                                className="rounded-lg bg-gray-50 px-3 py-2 text-sm dark:bg-gray-800"
                            >
                                <div className="font-medium text-gray-900 dark:text-gray-100">
                                    {PAGE_TYPE_LABELS[metric.page_type]}
                                </div>
                                <div className="mt-1 flex justify-between gap-3 text-xs text-gray-500 dark:text-gray-400">
                                    <span>
                                        検証済み {metric.verified_count} / {metric.total_count}
                                    </span>
                                    <span>
                                        CER{' '}
                                        {metric.aggregate_cer === null
                                            ? '—'
                                            : `${(metric.aggregate_cer * 100).toFixed(2)}%`}
                                    </span>
                                </div>
                            </div>
                        ))}
                </div>
            )}

            {corpusQuery.isError && (
                <Alert variant="error" className="m-4">
                    正解コーパスの取得に失敗しました。
                </Alert>
            )}
            {!corpusQuery.isLoading && corpus?.entries.length === 0 && (
                <div className="px-5 py-8 text-center text-sm text-gray-500">
                    評価ページはまだ登録されていません。
                </div>
            )}
            {corpus && corpus.entries.length > 0 && selected && (
                <div className="grid min-h-[600px] grid-cols-1 lg:grid-cols-[14rem_minmax(0,1fr)]">
                    <nav className="max-h-[720px] overflow-y-auto border-b border-gray-200 p-2 lg:border-r lg:border-b-0 dark:border-gray-700">
                        {corpus.entries.map((entry) => (
                            <button
                                type="button"
                                key={entry.id}
                                onClick={() => setSelectedId(entry.id)}
                                className={`mb-1 w-full rounded-md px-3 py-2 text-left text-sm ${
                                    entry.id === selectedId
                                        ? 'bg-primary-100 text-primary-800 dark:bg-primary-900/40 dark:text-primary-200'
                                        : 'hover:bg-gray-100 dark:hover:bg-gray-800'
                                }`}
                            >
                                <div className="truncate font-medium">{entry.book_name}</div>
                                <div className="flex items-center justify-between text-xs opacity-75">
                                    <span>画面 {entry.page_no}</span>
                                    <span>
                                        {entry.state === 'verified'
                                            ? entry.cer === null
                                                ? '検証済み'
                                                : `CER ${(entry.cer * 100).toFixed(1)}%`
                                            : '下書き'}
                                    </span>
                                </div>
                            </button>
                        ))}
                    </nav>

                    <div className="grid min-w-0 grid-cols-1 gap-4 p-4 xl:grid-cols-2">
                        <div>
                            <h3 className="mb-2 font-semibold">原画像 — 画面 {selected.page_no}</h3>
                            <div className="flex max-h-[560px] justify-center overflow-auto rounded-lg bg-gray-100 p-2 dark:bg-gray-950">
                                <img
                                    src={`${API_CONFIG.BASE_URL}${selected.image_url}`}
                                    alt={`${selected.book_name} 画面 ${selected.page_no}`}
                                    className="h-auto max-w-full object-contain"
                                />
                            </div>
                        </div>
                        <div className="flex min-w-0 flex-col gap-3">
                            <label className="flex items-center gap-3 text-sm">
                                ページ種別
                                <select
                                    value={pageType}
                                    onChange={(event) =>
                                        setPageType(event.target.value as OcrPageType)
                                    }
                                    className="rounded-lg border border-gray-300 bg-white px-3 py-2 dark:border-gray-600 dark:bg-gray-800"
                                >
                                    {Object.entries(PAGE_TYPE_LABELS).map(([value, label]) => (
                                        <option key={value} value={value}>
                                            {label}
                                        </option>
                                    ))}
                                </select>
                            </label>
                            <div>
                                <h3 className="mb-2 font-semibold">現在のOCR本文（比較用）</h3>
                                <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded-lg bg-gray-50 p-3 text-sm dark:bg-gray-950">
                                    {selected.ocr_text || '（本文なし）'}
                                </pre>
                            </div>
                            <label className="flex flex-1 flex-col text-sm font-semibold">
                                正解本文
                                <textarea
                                    value={referenceText}
                                    onChange={(event) => setReferenceText(event.target.value)}
                                    className="mt-2 min-h-64 flex-1 rounded-lg border border-gray-300 bg-white p-3 font-normal leading-7 dark:border-gray-600 dark:bg-gray-800"
                                    placeholder="原画像を見ながら正しい本文を転記してください"
                                />
                            </label>
                            <textarea
                                aria-label="正解コーパスメモ"
                                value={note}
                                onChange={(event) => setNote(event.target.value)}
                                className="min-h-16 rounded-lg border border-gray-300 bg-white p-2 text-sm dark:border-gray-600 dark:bg-gray-800"
                                placeholder="判読不能箇所・判断根拠など"
                            />
                            <div className="flex flex-wrap gap-2">
                                <button
                                    type="button"
                                    onClick={() => mutation.mutate('draft')}
                                    disabled={mutation.isPending}
                                    className="flex items-center gap-2 rounded-lg border border-gray-300 px-4 py-2 text-sm disabled:opacity-50 dark:border-gray-600"
                                >
                                    <Save className="h-4 w-4" />
                                    下書き保存
                                </button>
                                <button
                                    type="button"
                                    onClick={() => mutation.mutate('verified')}
                                    disabled={
                                        mutation.isPending ||
                                        pageType === 'unknown' ||
                                        referenceText.trim().length === 0
                                    }
                                    className="flex items-center gap-2 rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
                                >
                                    <CheckCircle2 className="h-4 w-4" />
                                    検証済みにする
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </section>
    );
}
