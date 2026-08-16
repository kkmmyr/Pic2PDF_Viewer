import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import { errorMessage } from '@/utils/error';

import { fetchOcrGroundTruth, updateOcrGroundTruth } from './api';
import type { OcrLayoutType, OcrPageType } from './types';

export function useOCRGroundTruthController() {
    const queryClient = useQueryClient();
    const [selectedId, setSelectedId] = useState<number | null>(null);
    const [referenceText, setReferenceText] = useState('');
    const [pageType, setPageType] = useState<OcrPageType>('unknown');
    const [layoutType, setLayoutType] = useState<OcrLayoutType>('unknown');
    const [note, setNote] = useState('');
    const corpusQuery = useQuery({ queryKey: ['ocrGroundTruth'], queryFn: fetchOcrGroundTruth });
    const corpus = corpusQuery.data;
    const selected = corpus?.entries.find((entry) => entry.id === selectedId);

    useEffect(() => {
        if (selectedId === null && corpus?.entries.length) setSelectedId(corpus.entries[0].id);
    }, [corpus, selectedId]);
    useEffect(() => {
        setReferenceText(selected?.reference_text ?? '');
        setPageType(selected?.page_type ?? 'unknown');
        setLayoutType(selected?.layout_type ?? 'unknown');
        setNote(selected?.note ?? '');
    }, [selected]);

    const mutation = useMutation({
        mutationFn: (state: 'draft' | 'verified') => {
            if (selectedId === null) throw new Error('評価ページが選択されていません');
            return updateOcrGroundTruth(selectedId, {
                reference_text: referenceText,
                page_type: pageType,
                layout_type: layoutType,
                state,
                note: note || null,
            });
        },
        onSuccess: async (_, state) => {
            toast.success(
                state === 'verified' ? '正解本文を検証済みにしました' : '下書きを保存しました',
            );
            await queryClient.invalidateQueries({ queryKey: ['ocrGroundTruth'] });
        },
        onError: (error: unknown) =>
            toast.error(errorMessage(error, '正解コーパスの保存に失敗しました。')),
    });

    return {
        corpusQuery,
        corpus,
        selected,
        selectedId,
        setSelectedId,
        referenceText,
        setReferenceText,
        pageType,
        setPageType,
        layoutType,
        setLayoutType,
        note,
        setNote,
        mutation,
    };
}
