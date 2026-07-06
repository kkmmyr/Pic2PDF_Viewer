/**
 * B-28 読書会 番組台本生成ページのロジック層。
 *
 * ホストキャラはレイ＆ミオ固定（サーバー側管理）のため、設定は書籍選択のみ。
 * state / effect / handler を集約し、NovelDiscussionPage は JSX の
 * オーケストレーターのみとなる。
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';

import {
    type DiscussionHistoryItem,
    deleteDiscussion,
    fetchDiscussionHistory,
} from '@/features/novel_db/api';
import {
    type DiscussionStage,
    type DiscussionTurnEvent,
    streamDiscussion,
} from '@/features/novel_db/sse';
import type { DiscussionChecks } from '@/features/novel_db/types';
import { errorMessage } from '@/utils/error';

// ---------------------------------------------------------------------------
// 公開型
// ---------------------------------------------------------------------------

export interface UseDiscussionReturn {
    // 書籍選択
    selectedBook: string;
    setSelectedBook: (v: string) => void;
    // 生成状態
    turns: DiscussionTurnEvent[];
    /** 受信済みセグメント id → 見出しタイトル。 */
    segments: Record<string, string>;
    /** 生成の進行段階。生成中以外は null。 */
    stage: DiscussionStage | null;
    /** 生成完了時の機械チェック結果。未完了・旧形式は null。 */
    checks: DiscussionChecks | null;
    isGenerating: boolean;
    error: string | null;
    // 派生値
    canGenerate: boolean;
    // 履歴
    history: DiscussionHistoryItem[];
    historyLoading: boolean;
    // ハンドラ
    handleGenerate: () => void;
    handleRegenerate: () => void;
    handleCancel: () => void;
    /** 履歴 1 件を削除して再取得する（確認 UI は呼び出し側の ConfirmDialog）。 */
    handleDelete: (filename: string) => Promise<void>;
    // refs
    bottomRef: React.RefObject<HTMLDivElement | null>;
}

// ---------------------------------------------------------------------------
// フック本体
// ---------------------------------------------------------------------------

export function useDiscussion(): UseDiscussionReturn {
    const [searchParams] = useSearchParams();

    const [selectedBook, setSelectedBook] = useState(() => searchParams.get('book') ?? '');

    const [turns, setTurns] = useState<DiscussionTurnEvent[]>([]);
    const [segments, setSegments] = useState<Record<string, string>>({});
    const [stage, setStage] = useState<DiscussionStage | null>(null);
    const [checks, setChecks] = useState<DiscussionChecks | null>(null);
    const [isGenerating, setIsGenerating] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const [history, setHistory] = useState<DiscussionHistoryItem[]>([]);
    const [historyLoading, setHistoryLoading] = useState(false);

    const abortRef = useRef<AbortController | null>(null);
    const bottomRef = useRef<HTMLDivElement>(null);

    const loadHistory = useCallback(async (bookName: string) => {
        if (!bookName) return;
        setHistoryLoading(true);
        try {
            const items = await fetchDiscussionHistory(bookName);
            setHistory(items);
        } catch {
            // 履歴なしは静かに無視
        } finally {
            setHistoryLoading(false);
        }
    }, []);

    // 書籍変更時に履歴を再取得
    useEffect(() => {
        void loadHistory(selectedBook);
    }, [selectedBook, loadHistory]);

    // 新ターン追加時にスクロール
    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [turns.length]);

    const handleGenerate = () => {
        if (!selectedBook || isGenerating) return;
        setTurns([]);
        setSegments({});
        setStage(null);
        setChecks(null);
        setError(null);
        setIsGenerating(true);

        const ctrl = new AbortController();
        abortRef.current = ctrl;

        void streamDiscussion(
            { book_name: selectedBook },
            {
                onStatus: (s) => setStage(s),
                onSegment: (ev) => setSegments((prev) => ({ ...prev, [ev.id]: ev.title })),
                onTurn: (ev) => setTurns((prev) => [...prev, ev]),
                onDone: (ev) => {
                    setChecks(ev.checks);
                    setStage(null);
                    setIsGenerating(false);
                    void loadHistory(selectedBook);
                },
                onError: (e) => {
                    setError(e.message);
                    setStage(null);
                    setIsGenerating(false);
                },
            },
            ctrl.signal,
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
                await deleteDiscussion(selectedBook, filename);
                toast.success('台本を削除しました');
                await loadHistory(selectedBook);
            } catch (e) {
                toast.error(errorMessage(e, '台本の削除に失敗しました'));
            }
        },
        [selectedBook, loadHistory],
    );

    const canGenerate = !!selectedBook && !isGenerating;

    return {
        selectedBook,
        setSelectedBook,
        turns,
        segments,
        stage,
        checks,
        isGenerating,
        error,
        canGenerate,
        history,
        historyLoading,
        handleGenerate,
        handleRegenerate: handleGenerate,
        handleCancel,
        handleDelete,
        bottomRef,
    };
}
