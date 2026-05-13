/**
 * B-20 読書会ディスカッション生成ページ（/novel/discussion）。
 *
 * 1 冊を選択し 2 人のペルソナ設定 + 発話数を指定して生成ボタンを押すと、
 * Qwen が読書会風の対話を SSE でリアルタイム配信する。
 * 生成完了後は自動保存され、過去の履歴も同ページで閲覧できる。
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { ChevronDown, ChevronUp, Loader2, MessageSquare, Square, Users } from 'lucide-react';

import {
    type DiscussionHistoryItem,
    fetchDiscussionHistory,
} from '../features/novel_db/api';
import {
    type DiscussionTurnEvent,
    streamDiscussion,
} from '../features/novel_db/sse';
import { useNovelDbBooks } from '../hooks/novel_db';

// ---------------------------------------------------------------------------
// ペルソナプリセット定義
// ---------------------------------------------------------------------------

const READING_STYLES = ['批評家', 'ファン', '懐疑派'] as const;
const TONES = ['敬語丁寧', 'フランク', '関西弁風'] as const;
const PERSPECTIVES = ['文学評論', '感情重視', 'ロジック重視'] as const;

interface PersonaState {
    name: string;
    readingStyle: string;
    tone: string;
    perspective: string;
    useCustom: boolean;
    customDesc: string;
}

function buildStyleDesc(p: PersonaState): string {
    if (p.useCustom) return p.customDesc.trim();
    return [p.readingStyle, p.tone, p.perspective].filter(Boolean).join('・');
}

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
// サブコンポーネント: ペルソナ設定パネル
// ---------------------------------------------------------------------------

interface PersonaPanelProps {
    label: string;
    persona: PersonaState;
    onChange: (p: PersonaState) => void;
    disabled?: boolean;
}

function PersonaPanel({ label, persona, onChange, disabled }: PersonaPanelProps) {
    const set = (patch: Partial<PersonaState>) => onChange({ ...persona, ...patch });

    return (
        <div className="flex-1 border border-gray-200 dark:border-gray-700 rounded-lg p-3 space-y-2.5">
            <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                {label}
            </p>
            <div>
                <label className="text-xs text-gray-500 dark:text-gray-400">名前</label>
                <input
                    type="text"
                    value={persona.name}
                    onChange={(e) => set({ name: e.target.value })}
                    disabled={disabled}
                    className="mt-0.5 w-full text-sm border border-gray-300 dark:border-gray-600 rounded px-2 py-1 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 disabled:opacity-50"
                    maxLength={50}
                />
            </div>

            <div className="flex items-center gap-2">
                <span className="text-xs text-gray-500 dark:text-gray-400">スタイル</span>
                <button
                    type="button"
                    onClick={() => set({ useCustom: !persona.useCustom })}
                    disabled={disabled}
                    className="text-xs text-accent-600 dark:text-accent-400 hover:underline disabled:opacity-50"
                >
                    {persona.useCustom ? 'プリセットに戻す' : 'カスタム入力'}
                </button>
            </div>

            {persona.useCustom ? (
                <textarea
                    value={persona.customDesc}
                    onChange={(e) => set({ customDesc: e.target.value })}
                    disabled={disabled}
                    placeholder="例: 哲学的な観点から問い直す、ですます調"
                    rows={2}
                    className="w-full text-xs border border-gray-300 dark:border-gray-600 rounded px-2 py-1 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 disabled:opacity-50 resize-none"
                    maxLength={200}
                />
            ) : (
                <div className="space-y-1.5">
                    <PresetRow
                        label="読書スタイル"
                        options={READING_STYLES}
                        value={persona.readingStyle}
                        onChange={(v) => set({ readingStyle: v })}
                        disabled={disabled}
                    />
                    <PresetRow
                        label="口調"
                        options={TONES}
                        value={persona.tone}
                        onChange={(v) => set({ tone: v })}
                        disabled={disabled}
                    />
                    <PresetRow
                        label="視点"
                        options={PERSPECTIVES}
                        value={persona.perspective}
                        onChange={(v) => set({ perspective: v })}
                        disabled={disabled}
                    />
                </div>
            )}

            <p className="text-xs text-gray-400 dark:text-gray-500 italic">
                → {buildStyleDesc(persona) || '（未設定）'}
            </p>
        </div>
    );
}

interface PresetRowProps {
    label: string;
    options: readonly string[];
    value: string;
    onChange: (v: string) => void;
    disabled?: boolean;
}

function PresetRow({ label, options, value, onChange, disabled }: PresetRowProps) {
    return (
        <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-xs text-gray-400 dark:text-gray-500 w-14 shrink-0">{label}</span>
            {options.map((opt) => (
                <button
                    key={opt}
                    type="button"
                    onClick={() => onChange(opt)}
                    disabled={disabled}
                    className={`text-xs px-2 py-0.5 rounded-full border transition-colors disabled:opacity-50 ${
                        value === opt
                            ? 'bg-accent-600 border-accent-600 text-white dark:bg-accent-500 dark:border-accent-500'
                            : 'border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 hover:border-accent-400'
                    }`}
                >
                    {opt}
                </button>
            ))}
        </div>
    );
}

// ---------------------------------------------------------------------------
// サブコンポーネント: ターン表示カード
// ---------------------------------------------------------------------------

interface TurnCardProps {
    speaker: 'A' | 'B';
    text: string;
    nameA: string;
    nameB: string;
}

function TurnCard({ speaker, text, nameA, nameB }: TurnCardProps) {
    const isA = speaker === 'A';
    return (
        <div
            className={`flex gap-2.5 ${isA ? '' : 'flex-row-reverse'}`}
        >
            <div
                className={`w-8 h-8 shrink-0 rounded-full flex items-center justify-center text-xs font-bold text-white ${
                    isA ? 'bg-indigo-500' : 'bg-emerald-500'
                }`}
            >
                {speaker}
            </div>
            <div
                className={`flex-1 max-w-[85%] rounded-xl px-3.5 py-2.5 text-sm leading-relaxed ${
                    isA
                        ? 'bg-indigo-50 dark:bg-indigo-900/30 text-indigo-900 dark:text-indigo-100 rounded-tl-sm'
                        : 'bg-emerald-50 dark:bg-emerald-900/30 text-emerald-900 dark:text-emerald-100 rounded-tr-sm'
                }`}
            >
                <p className="text-xs font-medium mb-1 opacity-70">{isA ? nameA : nameB}</p>
                <p className="whitespace-pre-wrap">{text}</p>
            </div>
        </div>
    );
}

// ---------------------------------------------------------------------------
// サブコンポーネント: 履歴アイテム
// ---------------------------------------------------------------------------

function HistoryItemCard({ item }: { item: DiscussionHistoryItem }) {
    const [open, setOpen] = useState(false);
    const nameA = item.personas[0]?.name ?? 'A';
    const nameB = item.personas[1]?.name ?? 'B';
    const dateStr = item.created_at ? item.created_at.slice(0, 16).replace('T', ' ') : '';

    return (
        <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
            <button
                type="button"
                onClick={() => setOpen((v) => !v)}
                className="w-full flex items-center justify-between px-3 py-2 bg-gray-50 dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
            >
                <div className="flex items-center gap-2 text-sm">
                    <Users className="w-3.5 h-3.5 text-gray-400" />
                    <span className="font-medium text-gray-800 dark:text-gray-200">
                        {nameA} × {nameB}
                    </span>
                    <span className="text-xs text-gray-400">（{item.turn_count} ターン）</span>
                    {dateStr && (
                        <span className="text-xs text-gray-400">{dateStr}</span>
                    )}
                </div>
                {open ? (
                    <ChevronUp className="w-4 h-4 text-gray-400" />
                ) : (
                    <ChevronDown className="w-4 h-4 text-gray-400" />
                )}
            </button>
            {open && (
                <div className="px-3 py-3 space-y-3">
                    {item.turns.map((t, i) => (
                        <TurnCard
                            key={i}
                            speaker={t.speaker as 'A' | 'B'}
                            text={t.text}
                            nameA={nameA}
                            nameB={nameB}
                        />
                    ))}
                </div>
            )}
        </div>
    );
}

// ---------------------------------------------------------------------------
// メインページ
// ---------------------------------------------------------------------------

export default function NovelDiscussionPage() {
    const { books } = useNovelDbBooks();

    const [selectedBook, setSelectedBook] = useState('');
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
    const canGenerate = !!selectedBook && !isGenerating && buildStyleDesc(personaA) && buildStyleDesc(personaB);

    return (
        <div className="max-w-3xl mx-auto px-4 sm:px-6 py-6 space-y-6">
            {/* ヘッダー */}
            <div className="flex items-center gap-2">
                <MessageSquare className="w-5 h-5 text-indigo-500" />
                <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100">
                    読書会ディスカッション
                </h1>
            </div>

            {/* 設定パネル */}
            <div className="space-y-4 border border-gray-200 dark:border-gray-700 rounded-xl p-4">
                {/* 書籍選択 */}
                <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                        書籍を選択
                    </label>
                    <select
                        value={selectedBook}
                        onChange={(e) => setSelectedBook(e.target.value)}
                        disabled={isGenerating}
                        className="w-full text-sm border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 disabled:opacity-50"
                    >
                        <option value="">— 書籍を選んでください —</option>
                        {books.map((b) => (
                            <option key={b.name} value={b.name}>
                                {b.name}
                                {b.series_id ? ` [${b.series_id}${b.volume != null ? ` ${b.volume}巻` : ''}]` : ''}
                            </option>
                        ))}
                    </select>
                </div>

                {/* ペルソナ設定 */}
                <div className="flex gap-3">
                    <PersonaPanel
                        label="キャラクター A"
                        persona={personaA}
                        onChange={setPersonaA}
                        disabled={isGenerating}
                    />
                    <PersonaPanel
                        label="キャラクター B"
                        persona={personaB}
                        onChange={setPersonaB}
                        disabled={isGenerating}
                    />
                </div>

                {/* 発話数スライダー */}
                <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                        往復数: <span className="text-indigo-600 dark:text-indigo-400">{numTurns}</span> 往復
                        （合計 {numTurns * 2} 発言）
                    </label>
                    <input
                        type="range"
                        min={2}
                        max={20}
                        step={1}
                        value={numTurns}
                        onChange={(e) => setNumTurns(Number(e.target.value))}
                        disabled={isGenerating}
                        className="w-full accent-indigo-600 disabled:opacity-50"
                    />
                    <div className="flex justify-between text-xs text-gray-400 mt-0.5">
                        <span>2往復</span>
                        <span>20往復</span>
                    </div>
                </div>

                {/* 生成 / キャンセルボタン */}
                <div className="flex gap-2">
                    <button
                        type="button"
                        onClick={handleGenerate}
                        disabled={!canGenerate}
                        className="flex-1 py-2 text-sm font-medium rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-2 transition-colors"
                    >
                        {isGenerating ? (
                            <>
                                <Loader2 className="w-4 h-4 animate-spin" />
                                生成中...
                            </>
                        ) : (
                            <>
                                <MessageSquare className="w-4 h-4" />
                                読書会を生成
                            </>
                        )}
                    </button>
                    {isGenerating && (
                        <button
                            type="button"
                            onClick={handleCancel}
                            className="px-4 py-2 text-sm font-medium rounded-lg border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 flex items-center gap-1.5 transition-colors"
                        >
                            <Square className="w-3.5 h-3.5" />
                            中止
                        </button>
                    )}
                </div>
            </div>

            {/* エラー表示 */}
            {error && (
                <div className="rounded-lg bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 px-4 py-3 text-sm text-red-700 dark:text-red-300">
                    {error}
                </div>
            )}

            {/* 現在の生成結果 */}
            {turns.length > 0 && (
                <section className="space-y-3">
                    <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300">
                        生成結果
                        {isGenerating && (
                            <span className="ml-2 text-xs text-gray-400 font-normal">生成中...</span>
                        )}
                    </h2>
                    <div className="space-y-3">
                        {turns.map((t, i) => (
                            <TurnCard
                                key={i}
                                speaker={t.speaker}
                                text={t.text}
                                nameA={nameA}
                                nameB={nameB}
                            />
                        ))}
                        <div ref={bottomRef} />
                    </div>
                </section>
            )}

            {/* 履歴セクション */}
            {selectedBook && (
                <section className="space-y-3">
                    <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300">
                        過去の生成履歴
                        {historyLoading && (
                            <Loader2 className="inline w-3.5 h-3.5 ml-2 animate-spin text-gray-400" />
                        )}
                    </h2>
                    {history.length === 0 && !historyLoading ? (
                        <p className="text-sm text-gray-400 dark:text-gray-500">履歴はありません。</p>
                    ) : (
                        <div className="space-y-2">
                            {history.map((item) => (
                                <HistoryItemCard key={item.filename} item={item} />
                            ))}
                        </div>
                    )}
                </section>
            )}
        </div>
    );
}
