import { useEffect, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import { errorMessage } from '@/utils/error';

import {
    approveOcrQaRun,
    classifyOcrQaPages,
    fetchOcrQaRun,
    fetchOcrQaRuns,
    reviewOcrQaPage,
} from './api';
import type { OcrLayoutType, OcrPageType, OcrSelectedEngine } from './types';

export function useOCRQaController() {
    const queryClient = useQueryClient();
    const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
    const [selectedPageNo, setSelectedPageNo] = useState<number | null>(null);
    const [note, setNote] = useState('');
    const [reviewer, setReviewer] = useState('local-user');
    const [showAll, setShowAll] = useState(false);
    const [pageType, setPageType] = useState<OcrPageType>('unknown');
    const [layoutType, setLayoutType] = useState<OcrLayoutType>('unknown');
    const [selectedEngine, setSelectedEngine] = useState<OcrSelectedEngine>('primary');
    const [correctedText, setCorrectedText] = useState('');
    const reviewStartedAtRef = useRef<string | null>(null);
    const reviewStartedMsRef = useRef<number | null>(null);
    const correctionStartedMsRef = useRef<number | null>(null);

    const runsQuery = useQuery({
        queryKey: ['ocrQaRuns'],
        queryFn: fetchOcrQaRuns,
        refetchInterval: 5000,
    });
    const awaitingRuns = useMemo(
        () => runsQuery.data?.runs.filter((run) => run.state === 'awaiting_qa') ?? [],
        [runsQuery.data],
    );

    useEffect(() => {
        if (selectedRunId === null && awaitingRuns.length > 0) {
            setSelectedRunId(awaitingRuns[0].id);
        }
    }, [awaitingRuns, selectedRunId]);

    const detailQuery = useQuery({
        queryKey: ['ocrQaRun', selectedRunId],
        queryFn: () => fetchOcrQaRun(selectedRunId as number),
        enabled: selectedRunId !== null,
    });
    const detail = detailQuery.data;
    const visiblePages = useMemo(
        () =>
            detail?.pages.filter(
                (page) => showAll || ['required', 'rejected'].includes(page.qa_state),
            ) ?? [],
        [detail, showAll],
    );

    useEffect(() => {
        if (visiblePages.length === 0) {
            setSelectedPageNo(null);
            return;
        }
        if (!visiblePages.some((page) => page.page_no === selectedPageNo)) {
            setSelectedPageNo(visiblePages[0].page_no);
        }
    }, [selectedPageNo, visiblePages]);

    const selectedPage = detail?.pages.find((page) => page.page_no === selectedPageNo);
    useEffect(() => {
        const now = Date.now();
        reviewStartedAtRef.current = selectedPage ? new Date(now).toISOString() : null;
        reviewStartedMsRef.current = selectedPage ? now : null;
        correctionStartedMsRef.current = null;
        setNote(selectedPage?.qa_note ?? '');
        setPageType(selectedPage?.page_type ?? 'unknown');
        setLayoutType(selectedPage?.layout_type ?? 'unknown');
        setSelectedEngine(selectedPage?.selected_engine ?? 'primary');
        setCorrectedText(
            selectedPage?.corrected_text ??
                (selectedPage?.selected_engine === 'external'
                    ? selectedPage.external_text
                    : (selectedPage?.primary_text ?? '')),
        );
    }, [selectedPage]);

    useEffect(() => {
        if (selectedEngine === 'codex' && correctionStartedMsRef.current === null) {
            correctionStartedMsRef.current = Date.now();
        }
        if (selectedEngine !== 'codex') {
            correctionStartedMsRef.current = null;
        }
    }, [selectedEngine]);

    const refresh = async () => {
        await Promise.all([
            queryClient.invalidateQueries({ queryKey: ['ocrQaRuns'] }),
            queryClient.invalidateQueries({ queryKey: ['ocrQaRun', selectedRunId] }),
        ]);
    };
    const pageMutation = useMutation({
        mutationFn: (state: 'approved' | 'rejected') => {
            const now = Date.now();
            return reviewOcrQaPage(
                selectedRunId as number,
                selectedPageNo as number,
                state,
                note || null,
                pageType,
                layoutType,
                selectedEngine,
                selectedEngine === 'codex' ? correctedText : null,
                reviewStartedAtRef.current,
                reviewStartedMsRef.current === null ? null : now - reviewStartedMsRef.current,
                selectedEngine === 'codex' && correctionStartedMsRef.current !== null
                    ? now - correctionStartedMsRef.current
                    : null,
            );
        },
        onSuccess: async (_, state) => {
            toast.success(state === 'approved' ? 'ページを承認しました' : 'ページを却下しました');
            await refresh();
        },
        onError: (error: unknown) =>
            toast.error(errorMessage(error, 'ページQAの保存に失敗しました。')),
    });
    const classifyMutation = useMutation({
        mutationFn: () => classifyOcrQaPages(selectedRunId as number),
        onSuccess: async () => {
            toast.success('ページ種別を自動判定しました');
            await refresh();
        },
        onError: (error: unknown) =>
            toast.error(errorMessage(error, 'ページ種別の自動判定に失敗しました。')),
    });
    const approveMutation = useMutation({
        mutationFn: () => approveOcrQaRun(selectedRunId as number, reviewer, null),
        onSuccess: async () => {
            toast.success('OCR本文を公開しました');
            setSelectedRunId(null);
            await refresh();
        },
        onError: (error: unknown) =>
            toast.error(errorMessage(error, 'OCR runの承認に失敗しました。')),
    });

    const canApproveRun =
        detail?.state === 'awaiting_qa' &&
        detail.required_pages === 0 &&
        detail.rejected_pages === 0 &&
        reviewer.trim().length > 0;

    return {
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
        detailQuery,
        detail,
        visiblePages,
        selectedPage,
        pageMutation,
        classifyMutation,
        approveMutation,
        canApproveRun,
    };
}
