/**
 * B-20 読書会ディスカッション生成ページのロジック層。
 *
 * state / effect / handler を集約し、NovelDiscussionPage は JSX の
 * オーケストレーターのみとなる。
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import { type PersonaState, buildStyleDesc } from '../../components/novel_db/PersonaPanel';
import { type DiscussionHistoryItem, fetchDiscussionHistory } from '../../features/novel_db/api';
import { type DiscussionTurnEvent, streamDiscussion } from '../../features/novel_db/sse';

// ---------------------------------------------------------------------------
// ペルソナデフォルト値
// ---------------------------------------------------------------------------

const DEFAULT_A: PersonaState = {
    name: '批評家',
    readingStyle: '批評家',
    tone: '敬語丁寧',
    perspective: '文学評論',
    useCustom: false,
    customDesc: '',
};
const DEFAULT_B: PersonaState = {
    name: 'ファン',
    readingStyle: 'ファン',
    tone: 'フランク',
    perspective: '感情重視',
    useCustom: false,
    customDesc: '',
};

// ---------------------------------------------------------------------------
// 公開型
// ---------------------------------------------------------------------------

export interface UseDiscussionReturn {
    // 書籍選択
    selectedBook: string;
    setSelectedBook: (v: string) => void;
    // ペルソナ
    personaA: PersonaState;
    setPersonaA: (v: PersonaState) => void;
    personaB: PersonaState;
    setPersonaB: (v: PersonaState) => void;
    // 発話数
    numTurns: number;
    setNumTurns: (v: number) => void;
    // 生成状態
    turns: DiscussionTurnEvent[];
    isGenerating: boolean;
    error: string | null;
    // 派生値
    nameA: string;
    nameB: string;
    canGenerate: boolean;
    // 履歴
    history: DiscussionHistoryItem[];
    historyLoading: boolean;
    // ハンドラ
    handleGenerate: () => void;
    handleCancel: () => void;
    // refs
    bottomRef: React.RefObject<HTMLDivElement>;
}

// ---------------------------------------------------------------------------
// フック本体
// ---------------------------------------------------------------------------

export function useDiscussion(): UseDiscussionReturn {
    const [searchParams] = useSearchParams();

    const [selectedBook, setSelectedBook] = useState(() => searchParams.get('book') ?? '');
    const [personaA, setPersonaA] = useState<PersonaState>(DEFAULT_A);
    const [personaB, setPersonaB] = useState<PersonaState>(DEFAULT_B);
    const [numTurns, setNumTurns] = useState(6);

    const [turns, setTurns] = useState<DiscussionTurnEvent[]>([]);
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
        if (!selectedBook) return;
        setTurns([]);
        setError(null);
        setIsGenerating(true);

        const ctrl = new AbortController();
        abortRef.current = ctrl;

        void streamDiscussion(
            {
                book_name: selectedBook,
                personas: [
                    { name: personaA.name, style_description: buildStyleDesc(personaA) },
                    { name: personaB.name, style_description: buildStyleDesc(personaB) },
                ],
                num_turns: numTurns,
            },
            {
                onTurn: (ev) => setTurns((prev) => [...prev, ev]),
                onDone: () => {
                    setIsGenerating(false);
                    void loadHistory(selectedBook);
                },
                onError: (e) => {
                    setError(e.message);
                    setIsGenerating(false);
                },
            },
            ctrl.signal,
        );
    };

    const handleCancel = () => {
        abortRef.current?.abort();
        setIsGenerating(false);
    };

    const nameA = personaA.name || 'A';
    const nameB = personaB.name || 'B';
    const canGenerate =
        !!selectedBook &&
        !isGenerating &&
        buildStyleDesc(personaA) !== '' &&
        buildStyleDesc(personaB) !== '';

    return {
        selectedBook,
        setSelectedBook,
        personaA,
        setPersonaA,
        personaB,
        setPersonaB,
        numTurns,
        setNumTurns,
        turns,
        isGenerating,
        error,
        nameA,
        nameB,
        canGenerate,
        history,
        historyLoading,
        handleGenerate,
        handleCancel,
        bottomRef,
    };
}
