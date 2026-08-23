import { useState } from 'react';

import { Check, Eye, RefreshCw, ShieldCheck, X } from 'lucide-react';

import { Alert } from '@/components/ui/alert';
import { API_CONFIG } from '@/config/api';
import {
    getOcrEngineLabels,
    getSelectionReasonLabel,
    LAYOUT_TYPE_LABELS,
    PAGE_TYPE_LABELS,
} from '@/features/ocr/ocrQaLabels';

import type { OcrLayoutType, OcrPageType, OcrSelectedEngine } from './types';
import { useOCRQaController } from './useOCRQaController';

type ImageZoom = 'fit' | 'double';

export function OCRQaPanel() {
    const [imageZoom, setImageZoom] = useState<ImageZoom>('double');
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
    const engineLabels = getOcrEngineLabels(detail?.engine);

    return (
        <section className="rounded-xl border border-gray-200 bg-white shadow-sm dark:border-gray-700 dark:bg-gray-900">
            <header className="flex flex-wrap items-center gap-3 border-b border-gray-200 px-5 py-4 dark:border-gray-700">
                <ShieldCheck className="h-5 w-5 text-primary-600 dark:text-primary-400" />
                <div className="min-w-0 flex-1">
                    <h2 className="font-bold text-gray-900 dark:text-gray-100">OCR 品質確認</h2>
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                        原画像とOCR本文を確認後に公開します。QA未承認ではFull Buildできません。
                    </p>
                </div>
                <select
                    aria-label="QA対象run"
                    value={selectedRunId ?? ''}
                    onChange={(event) => setSelectedRunId(Number(event.target.value))}
                    className="max-w-sm rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800"
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
                        <span>要確認 {detail.required_pages}</span>
                        <span className="text-green-700 dark:text-green-400">
                            承認 {detail.approved_pages}
                        </span>
                        <span className="text-red-700 dark:text-red-400">
                            却下 {detail.rejected_pages}
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
                                    {page.qa_state === 'approved' && (
                                        <Check className="h-4 w-4 text-green-600" />
                                    )}
                                    {page.qa_state === 'rejected' && (
                                        <X className="h-4 w-4 text-red-600" />
                                    )}
                                </button>
                            ))}
                        </nav>

                        {selectedPage ? (
                            <div
                                className={`grid min-w-0 grid-cols-1 gap-4 p-4 ${
                                    imageZoom === 'fit'
                                        ? 'xl:grid-cols-[minmax(0,1fr)_minmax(18rem,1fr)]'
                                        : ''
                                }`}
                            >
                                <div className="min-w-0">
                                    <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                                        <h3 className="font-semibold">
                                            原画像 — 画面 {selectedPage.page_no}
                                        </h3>
                                        <div
                                            role="group"
                                            aria-label="原画像の表示倍率"
                                            className="flex rounded-lg border border-gray-300 p-0.5 dark:border-gray-600"
                                        >
                                            {(
                                                [
                                                    ['fit', '画面幅'],
                                                    ['double', '2倍'],
                                                ] as const
                                            ).map(([value, label]) => (
                                                <button
                                                    key={value}
                                                    type="button"
                                                    aria-pressed={imageZoom === value}
                                                    onClick={() => setImageZoom(value)}
                                                    className={`rounded-md px-2.5 py-1 text-xs font-medium ${
                                                        imageZoom === value
                                                            ? 'bg-primary-600 text-white'
                                                            : 'text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800'
                                                    }`}
                                                >
                                                    {label}
                                                </button>
                                            ))}
                                        </div>
                                    </div>
                                    <div
                                        key={selectedPage.page_no}
                                        role="region"
                                        // Scroll regions need focus so arrow keys work without a pointer.
                                        // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex
                                        tabIndex={0}
                                        aria-label="拡大した原画像。上下方向はホイール、トラックパッド、矢印キーで移動できます"
                                        className="h-[calc(100dvh-8rem)] min-h-[640px] max-h-[1200px] overflow-x-hidden overflow-y-auto rounded-lg bg-gray-100 p-2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-500 dark:bg-gray-950"
                                    >
                                        <img
                                            src={`${API_CONFIG.BASE_URL}${selectedPage.image_url}`}
                                            alt={`${detail.book_name} 画面 ${selectedPage.page_no}`}
                                            className="h-auto w-full object-contain"
                                        />
                                    </div>
                                </div>
                                <div className="flex min-w-0 flex-col">
                                    <h3 className="mb-2 font-semibold">OCR本文</h3>
                                    <div className="mb-2 flex flex-wrap gap-1">
                                        {selectedPage.quality_flags.map((flag) => (
                                            <span
                                                key={flag}
                                                className="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-800 dark:bg-amber-900/40 dark:text-amber-200"
                                            >
                                                {flag}
                                            </span>
                                        ))}
                                    </div>
                                    {selectedPage.selection_reason && (
                                        <p className="mb-3 rounded-md border border-blue-200 bg-blue-50 px-3 py-2 text-xs text-blue-800 dark:border-blue-800 dark:bg-blue-950/40 dark:text-blue-200">
                                            初期候補の選択理由:{' '}
                                            {getSelectionReasonLabel(selectedPage.selection_reason)}
                                            <span className="ml-1 font-mono text-[11px] opacity-75">
                                                ({selectedPage.selection_reason})
                                            </span>
                                        </p>
                                    )}
                                    <div className="grid gap-2">
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
                                                {Object.entries(engineLabels).map(
                                                    ([value, label]) => (
                                                        <option key={value} value={value}>
                                                            {label}
                                                        </option>
                                                    ),
                                                )}
                                            </select>
                                        </label>
                                        <textarea
                                            aria-label="採用OCR本文"
                                            value={
                                                selectedEngine === 'primary'
                                                    ? selectedPage.primary_text
                                                    : selectedEngine === 'external'
                                                      ? selectedPage.external_text
                                                      : correctedText
                                            }
                                            readOnly={selectedEngine !== 'codex'}
                                            onChange={(event) =>
                                                setCorrectedText(event.target.value)
                                            }
                                            className="min-h-[280px] max-h-[400px] flex-1 overflow-auto whitespace-pre-wrap rounded-lg border border-gray-200 bg-gray-50 p-3 text-sm leading-7 read-only:opacity-80 dark:border-gray-700 dark:bg-gray-950"
                                        />
                                        {!selectedPage.external_text && (
                                            <p className="text-xs text-amber-700 dark:text-amber-300">
                                                この画面には{engineLabels.external}
                                                が保存されていません。
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
                                            <Check className="h-4 w-4" /> 承認
                                        </button>
                                        <button
                                            type="button"
                                            onClick={() => pageMutation.mutate('rejected')}
                                            disabled={pageMutation.isPending}
                                            className="flex items-center gap-2 rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
                                        >
                                            <X className="h-4 w-4" /> 却下
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
