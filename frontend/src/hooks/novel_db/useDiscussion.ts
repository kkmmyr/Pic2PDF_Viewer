import { useCallback, useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';

import {
    type DiscussionHistoryItem,
    deleteDiscussion,
    fetchDiscussionHistory,
} from '@/features/novel_db/api';
import { novelDbKeys } from '@/features/novel_db/queries';
import {
    type DiscussionStage,
    type DiscussionTurnEvent,
    streamDiscussion,
} from '@/features/novel_db/discussion-sse';
import type { DiscussionChecks } from '@/features/novel_db/types';
import { errorMessage } from '@/utils/error';

export interface UseDiscussionReturn {
    selectedBook: string;
    setSelectedBook: (v: string) => void;
    turns: DiscussionTurnEvent[];
    segments: Record<string, string>;
    stage: DiscussionStage | null;
    checks: DiscussionChecks | null;
    isGenerating: boolean;
    error: string | null;
    canGenerate: boolean;
    history: DiscussionHistoryItem[];
    historyLoading: boolean;
    handleGenerate: () => void;
    handleRegenerate: () => void;
    handleCancel: () => void;
    handleDelete: (filename: string) => Promise<void>;
    bottomRef: React.RefObject<HTMLDivElement | null>;
}

export function useDiscussion(): UseDiscussionReturn {
    const [searchParams] = useSearchParams();
    const queryClient = useQueryClient();
    const [selectedBook, setSelectedBook] = useState(() => searchParams.get('book') ?? '');
    const [turns, setTurns] = useState<DiscussionTurnEvent[]>([]);
    const [segments, setSegments] = useState<Record<string, string>>({});
    const [stage, setStage] = useState<DiscussionStage | null>(null);
    const [checks, setChecks] = useState<DiscussionChecks | null>(null);
    const [isGenerating, setIsGenerating] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const abortRef = useRef<AbortController | null>(null);
    const bottomRef = useRef<HTMLDivElement>(null);
    const historyQueryKey = novelDbKeys.discussions(selectedBook);

    const historyQuery = useQuery({
        queryKey: historyQueryKey,
        queryFn: () => fetchDiscussionHistory(selectedBook),
        enabled: selectedBook.length > 0,
    });
    const deleteMutation = useMutation({
        mutationFn: (filename: string) => deleteDiscussion(selectedBook, filename),
        onSuccess: async () => {
            toast.success('台本を削除しました');
            await queryClient.invalidateQueries({ queryKey: historyQueryKey });
        },
        onError: (mutationError) => {
            toast.error(errorMessage(mutationError, '台本の削除に失敗しました'));
        },
    });

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [turns.length]);

    useEffect(
        () => () => {
            abortRef.current?.abort();
        },
        [],
    );

    const handleGenerate = () => {
        if (!selectedBook || isGenerating) return;
        setTurns([]);
        setSegments({});
        setStage(null);
        setChecks(null);
        setError(null);
        setIsGenerating(true);

        const controller = new AbortController();
        abortRef.current = controller;
        void streamDiscussion(
            { book_name: selectedBook },
            {
                onStatus: setStage,
                onSegment: (event) =>
                    setSegments((previous) => ({ ...previous, [event.id]: event.title })),
                onTurn: (event) => setTurns((previous) => [...previous, event]),
                onDone: (event) => {
                    setChecks(event.checks);
                    setStage(null);
                    setIsGenerating(false);
                    void queryClient.resetQueries({
                        queryKey: historyQueryKey,
                        exact: true,
                    });
                },
                onError: (streamError) => {
                    setError(streamError.message);
                    setStage(null);
                    setIsGenerating(false);
                },
            },
            controller.signal,
        );
    };

    const handleCancel = () => {
        abortRef.current?.abort();
        setStage(null);
        setIsGenerating(false);
    };

    const handleDelete = useCallback(
        async (filename: string) => {
            try {
                await deleteMutation.mutateAsync(filename);
            } catch {
                // onError handles user-facing notification.
            }
        },
        [deleteMutation],
    );

    return {
        selectedBook,
        setSelectedBook,
        turns,
        segments,
        stage,
        checks,
        isGenerating,
        error,
        canGenerate: selectedBook.length > 0 && !isGenerating,
        history: historyQuery.data ?? [],
        historyLoading: historyQuery.isLoading,
        handleGenerate,
        handleRegenerate: handleGenerate,
        handleCancel,
        handleDelete,
        bottomRef,
    };
}
