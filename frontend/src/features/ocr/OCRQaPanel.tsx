import { Check, Eye, RefreshCw, ShieldCheck, X } from 'lucide-react';

import { Alert } from '@/components/ui/alert';
import { API_CONFIG } from '@/config/api';
import {
    compactTextLength,
    ENGINE_LABELS,
    formatDurationMs,
    LAYOUT_TYPE_LABELS,
    PAGE_TYPE_LABELS,
    qaDecisionLabel,
    qualityFlagLabel,
    runtimeManifestLabel,
} from '@/features/ocr/ocrQaPresentation';

import type { OcrLayoutType, OcrPageType, OcrSelectedEngine } from './types';
import { useOCRQaController } from './useOCRQaController';

export function OCRQaPanel() {
    const {
        runsQuery,
        awaitingRuns,
        selectedRunId,
        setSelectedRunId,
        selectedPageNo,
        setSelectedPageNo,
        note,
        setNote,
        reviewer,
        setReviewer,
        showAll,
        setShowAll,
        pageType,
        setPageType,
        layoutType,
        setLayoutType,
        selectedEngine,
        setSelectedEngine,
        correctedText,
        setCorrectedText,
        detail,
        visiblePages,
        selectedPage,
        pageMutation,
        classifyMutation,
        approveMutation,
        canApproveRun,
    } = useOCRQaController();
    const primaryLength = compactTextLength(selectedPage?.primary_text ?? '');
    const externalLength = compactTextLength(selectedPage?.external_text ?? '');
    const externalLengthDifference = externalLength - primaryLength;

    return (
        <section className="rounded-xl border border-gray-200 bg-white shadow-sm dark:border-gray-700 dark:bg-gray-900">
            <header className="flex flex-col items-stretch gap-3 border-b border-gray-200 px-5 py-4 sm:flex-row sm:items-center dark:border-gray-700">
                <div className="flex min-w-0 items-start gap-3 sm:flex-1">
                    <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-primary-600 dark:text-primary-400" />
                    <div className="min-w-0">
                        <h2 className="font-bold text-gray-900 dark:text-gray-100">OCR 品質確認</h2>
                        <p className="text-sm text-gray-500 dark:text-gray-400">
                            全ページを原画像と照合し、OK・修正・保留のいずれかを記録します。
                        </p>
                    </div>
                </div>
                <select
                    aria-label="QA対象run"
                    value={selectedRunId ?? ''}
                    onChange={(event) => setSelectedRunId(Number(event.target.value))}
                    className="w-full max-w-sm rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm sm:w-auto dark:border-gray-600 dark:bg-gray-800"
                >
                    <option value="">対象を選択</option>
                    {awaitingRuns.map((run) => (
                        <option key={run.id} value={run.id}>
                            {run.book_name}（残り{run.required_pages}）
                        </option>
                    ))}
                </select>
            </header>

            {runsQuery.isError && (
                <Alert variant="error" className="m-4">
                    QA対象の取得に失敗しました。
                </Alert>
            )}
            {!runsQuery.isLoading && awaitingRuns.length === 0 && (
                <div className="px-5 py-8 text-center text-sm text-gray-500">
                    品質確認待ちのOCR結果はありません。
                </div>
            )}
            {detail && (
                <>
                    <div className="flex flex-wrap items-center gap-3 border-b border-gray-200 px-5 py-3 text-sm dark:border-gray-700">
                        <span>未確認 {detail.required_pages}</span>
                        <span className="text-green-700 dark:text-green-400">
                            OK・修正 {detail.approved_pages}
                        </span>
                        <span className="text-red-700 dark:text-red-400">
                            保留 {detail.rejected_pages}
                        </span>
                        <span className="basis-full text-xs text-gray-500 dark:text-gray-400">
                            実行版: {runtimeManifestLabel(detail.runtime_manifest)} / 初期化{' '}
                            {formatDurationMs(detail.timing.worker_init_ms)}
                        </span>
                        <label className="ml-auto flex items-center gap-2">
                            <input
                                type="checkbox"
                                checked={showAll}
                                onChange={(event) => setShowAll(event.target.checked)}
                            />
                            全ページ表示
                        </label>
                        <button
                            type="button"
                            onClick={() => classifyMutation.mutate()}
                            disabled={classifyMutation.isPending}
                            className="flex items-center gap-2 rounded-lg border border-gray-300 px-3 py-1.5 text-sm disabled:opacity-50 dark:border-gray-600"
                        >
                            <RefreshCw className="h-4 w-4" />
                            種別を自動判定
                        </button>
                    </div>

                    <div className="grid min-h-[560px] grid-cols-1 lg:grid-cols-[12rem_minmax(0,1fr)]">
                        <nav
                            aria-label="OCR QAページ"
                            className="max-h-[650px] overflow-y-auto border-b border-gray-200 p-2 lg:border-r lg:border-b-0 dark:border-gray-700"
                        >
                            {visiblePages.map((page) => (
                                <button
                                    type="button"
                                    key={page.page_no}
                                    onClick={() => setSelectedPageNo(page.page_no)}
                                    className={`mb-1 flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm ${
                                        page.page_no === selectedPageNo
                                            ? 'bg-primary-100 text-primary-800 dark:bg-primary-900/40 dark:text-primary-200'
                                            : 'hover:bg-gray-100 dark:hover:bg-gray-800'
                                    }`}
                                >
                                    <Eye className="h-4 w-4" />
                                    <span className="flex-1">画面 {page.page_no}</span>
                                    <span
                                        className={`text-xs font-medium ${
                                            page.qa_state === 'approved'
                                                ? 'text-green-700 dark:text-green-400'
                                                : page.qa_state === 'rejected'
                                                  ? 'text-red-700 dark:text-red-400'
                                                  : 'text-amber-700 dark:text-amber-300'
                                        }`}
                                    >
                                        {qaDecisionLabel(page.qa_state, page.selected_engine)}
                                    </span>
                                </button>
                            ))}
                        </nav>

                        {selectedPage ? (
                            <div className="grid min-w-0 grid-cols-1 gap-4 p-4 xl:grid-cols-2">
                                <div className="min-w-0">
                                    <h3 className="mb-2 font-semibold">
                                        原画像 — 画面 {selectedPage.page_no}
                                    </h3>
                                    <div className="flex max-h-[520px] justify-center overflow-auto rounded-lg bg-gray-100 p-2 dark:bg-gray-950">
                                        <img
                                            src={`${API_CONFIG.BASE_URL}${selectedPage.image_url}`}
                                            alt={`${detail.book_name} 画面 ${selectedPage.page_no}`}
                                            className="h-auto max-w-full object-contain"
                                        />
                                    </div>
                                </div>
                                <div className="flex min-w-0 flex-col">
                                    <div className="mb-2 flex flex-wrap items-center gap-2">
                                        <h3 className="font-semibold">OCR候補と確認理由</h3>
                                        <span className="rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-700 dark:bg-gray-800 dark:text-gray-300">
                                            機械判定 {selectedPage.state}
                                        </span>
                                        <span className="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-800 dark:bg-amber-900/40 dark:text-amber-200">
                                            QA{' '}
                                            {qaDecisionLabel(
                                                selectedPage.qa_state,
                                                selectedPage.selected_engine,
                                            )}
                                        </span>
                                        <span className="rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-700 dark:bg-gray-800 dark:text-gray-300">
                                            画面処理{' '}
                                            {formatDurationMs(
                                                selectedPage.processing_timing.total_ms,
                                            )}
                                        </span>
                                    </div>
                                    <div className="mb-2 flex flex-wrap gap-1">
                                        {selectedPage.quality_flags.map((flag) => (
                                            <span
                                                key={flag}
                                                title={flag}
                                                className="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-800 dark:bg-amber-900/40 dark:text-amber-200"
                                            >
                                                {qualityFlagLabel(flag)}
                                            </span>
                                        ))}
                                    </div>
                                    <div className="grid gap-2">
                                        <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                                            <section className="min-w-0 rounded-lg border border-gray-200 p-2 dark:border-gray-700">
                                                <h4 className="mb-1 text-sm font-medium">
                                                    Surya候補
                                                    <span className="ml-2 text-xs font-normal text-gray-500">
                                                        {primaryLength}文字
                                                    </span>
                                                </h4>
                                                <textarea
                                                    aria-label="Surya候補本文"
                                                    value={selectedPage.primary_text}
                                                    readOnly
                                                    className="min-h-40 w-full resize-y whitespace-pre-wrap rounded border border-gray-200 bg-gray-50 p-2 text-sm leading-6 dark:border-gray-700 dark:bg-gray-950"
                                                />
                                            </section>
                                            <section className="min-w-0 rounded-lg border border-gray-200 p-2 dark:border-gray-700">
                                                <h4 className="mb-1 text-sm font-medium">
                                                    yomitoku候補
                                                    <span className="ml-2 text-xs font-normal text-gray-500">
                                                        {externalLength}文字（Surya比
                                                        {externalLengthDifference >= 0 ? '+' : ''}
                                                        {externalLengthDifference}）
                                                    </span>
                                                </h4>
                                                <textarea
                                                    aria-label="yomitoku候補本文"
                                                    value={selectedPage.external_text}
                                                    readOnly
                                                    placeholder="候補なし"
                                                    className="min-h-40 w-full resize-y whitespace-pre-wrap rounded border border-gray-200 bg-gray-50 p-2 text-sm leading-6 dark:border-gray-700 dark:bg-gray-950"
                                                />
                                            </section>
                                        </div>
                                        <label className="flex items-center gap-3 text-sm">
                                            採用候補
                                            <select
                                                value={selectedEngine}
                                                onChange={(event) => {
                                                    const engine = event.target
                                                        .value as OcrSelectedEngine;
                                                    setSelectedEngine(engine);
                                                    if (engine === 'primary') {
                                                        setCorrectedText(selectedPage.primary_text);
                                                    } else if (engine === 'external') {
                                                        setCorrectedText(
                                                            selectedPage.external_text,
                                                        );
                                                    }
                                                }}
                                                className="rounded-lg border border-gray-300 bg-white px-3 py-2 dark:border-gray-600 dark:bg-gray-800"
                                            >
                                                {Object.entries(ENGINE_LABELS).map(
                                                    ([value, label]) => (
                                                        <option key={value} value={value}>
                                                            {label}
                                                        </option>
                                                    ),
                                                )}
                                            </select>
                                        </label>
                                        {selectedEngine === 'codex' ? (
                                            <textarea
                                                aria-label="Codex確認済み補正文"
                                                value={correctedText}
                                                onChange={(event) =>
                                                    setCorrectedText(event.target.value)
                                                }
                                                placeholder="原画像で確認した補正文を入力"
                                                className="min-h-48 max-h-[400px] flex-1 overflow-auto whitespace-pre-wrap rounded-lg border border-gray-200 bg-gray-50 p-3 text-sm leading-7 dark:border-gray-700 dark:bg-gray-950"
                                            />
                                        ) : (
                                            <p className="rounded-lg bg-blue-50 px-3 py-2 text-sm text-blue-800 dark:bg-blue-950/40 dark:text-blue-200">
                                                原画像と一致する候補を選び、「OKとして保存」してください。
                                            </p>
                                        )}
                                        {!selectedPage.external_text && (
                                            <p className="text-xs text-amber-700 dark:text-amber-300">
                                                この画面にはyomitoku候補が保存されていません。
                                            </p>
                                        )}
                                    </div>
                                    <label className="mt-3 flex items-center gap-3 text-sm">
                                        ページ種別
                                        <select
                                            value={pageType}
                                            onChange={(event) =>
                                                setPageType(event.target.value as OcrPageType)
                                            }
                                            className="rounded-lg border border-gray-300 bg-white px-3 py-2 dark:border-gray-600 dark:bg-gray-800"
                                        >
                                            {Object.entries(PAGE_TYPE_LABELS).map(
                                                ([value, label]) => (
                                                    <option key={value} value={value}>
                                                        {label}
                                                    </option>
                                                ),
                                            )}
                                        </select>
                                        <span className="text-xs text-gray-500">
                                            {pageType === 'narrative'
                                                ? '検索・要約の対象'
                                                : '検索・要約から除外'}
                                        </span>
                                    </label>
                                    <label className="mt-3 flex items-center gap-3 text-sm">
                                        レイアウト
                                        <select
                                            value={layoutType}
                                            onChange={(event) =>
                                                setLayoutType(event.target.value as OcrLayoutType)
                                            }
                                            className="rounded-lg border border-gray-300 bg-white px-3 py-2 dark:border-gray-600 dark:bg-gray-800"
                                        >
                                            {Object.entries(LAYOUT_TYPE_LABELS).map(
                                                ([value, label]) => (
                                                    <option key={value} value={value}>
                                                        {label}
                                                    </option>
                                                ),
                                            )}
                                        </select>
                                    </label>
                                    <textarea
                                        aria-label="QAメモ"
                                        value={note}
                                        onChange={(event) => setNote(event.target.value)}
                                        placeholder="誤読・欠落箇所などのメモ"
                                        className="mt-3 min-h-20 rounded-lg border border-gray-300 bg-white p-2 text-sm dark:border-gray-600 dark:bg-gray-800"
                                    />
                                    <div className="mt-3 flex gap-2">
                                        <button
                                            type="button"
                                            onClick={() => pageMutation.mutate('approved')}
                                            disabled={
                                                pageMutation.isPending ||
                                                pageType === 'unknown' ||
                                                layoutType === 'unknown' ||
                                                (selectedEngine === 'codex' &&
                                                    correctedText.trim().length === 0)
                                            }
                                            className="flex items-center gap-2 rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
                                        >
                                            <Check className="h-4 w-4" />{' '}
                                            {selectedEngine === 'codex'
                                                ? '修正として保存'
                                                : 'OKとして保存'}
                                        </button>
                                        <button
                                            type="button"
                                            onClick={() => pageMutation.mutate('rejected')}
                                            disabled={pageMutation.isPending}
                                            className="flex items-center gap-2 rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
                                        >
                                            <X className="h-4 w-4" /> 保留
                                        </button>
                                    </div>
                                </div>
                            </div>
                        ) : (
                            <div className="grid place-items-center p-8 text-sm text-gray-500">
                                要確認ページはすべて処理済みです。
                            </div>
                        )}
                    </div>

                    <footer className="flex flex-wrap items-center gap-3 border-t border-gray-200 px-5 py-4 dark:border-gray-700">
                        <label className="flex items-center gap-2 text-sm">
                            確認者
                            <input
                                value={reviewer}
                                onChange={(event) => setReviewer(event.target.value)}
                                className="rounded-lg border border-gray-300 bg-white px-3 py-2 dark:border-gray-600 dark:bg-gray-800"
                            />
                        </label>
                        <button
                            type="button"
                            onClick={() => approveMutation.mutate()}
                            disabled={!canApproveRun || approveMutation.isPending}
                            className="ml-auto rounded-lg bg-primary-600 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40"
                        >
                            QA承認して本文を公開
                        </button>
                    </footer>
                </>
            )}
        </section>
    );
}
