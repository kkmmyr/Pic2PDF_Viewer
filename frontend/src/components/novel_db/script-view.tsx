/**
 * 読書会 番組台本の共通表示コンポーネント群（B-28）。
 *
 * - TurnCard: 発言 1 件の吹き出し（A=レイ: indigo / B=ミオ: emerald）
 * - ScriptView: セグメント見出し付きの台本レンダリング（v1 はフラット表示）
 * - ChecksBadge: 機械チェックの合否バッジ
 * - ScriptExportButtons: クリップボードコピー + Markdown ダウンロード
 *
 * NovelDiscussionPage（生成結果）と DiscussionHistoryItem（履歴カード）の両方で使う。
 */
import { CheckCircle2, Copy, Download, TriangleAlert } from 'lucide-react';
import { toast } from 'sonner';

import {
    buildScriptMarkdown,
    downloadScriptMarkdown,
    SPEAKER_NAMES,
} from '@/features/novel_db/script-export';
import type { DiscussionChecks, DiscussionTurn } from '@/features/novel_db/types';

// ---------------------------------------------------------------------------
// TurnCard（発言吹き出し）
// ---------------------------------------------------------------------------

interface TurnCardProps {
    speaker: 'A' | 'B';
    text: string;
    nameA?: string;
    nameB?: string;
}

export function TurnCard({
    speaker,
    text,
    nameA = SPEAKER_NAMES.A,
    nameB = SPEAKER_NAMES.B,
}: TurnCardProps) {
    const isA = speaker === 'A';
    return (
        <div className={`flex gap-2.5 ${isA ? '' : 'flex-row-reverse'}`}>
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
// ScriptView（セグメント見出し付き台本表示）
// ---------------------------------------------------------------------------

interface ScriptViewProps {
    turns: DiscussionTurn[];
    /** セグメント id → 見出しタイトルのマップ。v1 データでは不要。 */
    segments?: Record<string, string> | null;
    /** 話者名の上書き（v1 履歴のペルソナ名表示用）。省略時はレイ / ミオ。 */
    nameA?: string;
    nameB?: string;
}

function SegmentDivider({ title }: { title: string }) {
    return (
        <div className="flex items-center gap-3 pt-2" role="separator" aria-label={title}>
            <div className="flex-1 h-px bg-gray-300 dark:bg-gray-600" />
            <span className="text-xs font-semibold text-gray-500 dark:text-gray-400 tracking-wide">
                {title}
            </span>
            <div className="flex-1 h-px bg-gray-300 dark:bg-gray-600" />
        </div>
    );
}

/** turns[0..i-1] の中で最後に現れた segment id を返す（区切り判定用の純関数）。 */
function lastSegmentBefore(turns: DiscussionTurn[], index: number): string | undefined {
    for (let j = index - 1; j >= 0; j--) {
        const seg = turns[j].segment;
        if (seg) return seg;
    }
    return undefined;
}

/**
 * 台本を順に描画する。turn.segment が直前と変わったところに区切り見出しを挿入する。
 * segment を持たない turn（v1 データ）は見出しなしで従来どおり表示する。
 */
export default function ScriptView({ turns, segments, nameA, nameB }: ScriptViewProps) {
    return (
        <div className="space-y-3">
            {turns.map((t, i) => {
                const showDivider = !!t.segment && t.segment !== lastSegmentBefore(turns, i);
                return (
                    <div key={i} className="space-y-3">
                        {showDivider && t.segment && (
                            <SegmentDivider title={segments?.[t.segment] ?? t.segment} />
                        )}
                        <TurnCard
                            speaker={t.speaker === 'B' ? 'B' : 'A'}
                            text={t.text}
                            nameA={nameA}
                            nameB={nameB}
                        />
                    </div>
                );
            })}
        </div>
    );
}

// ---------------------------------------------------------------------------
// ChecksBadge（機械チェック合否バッジ）
// ---------------------------------------------------------------------------

interface ChecksBadgeProps {
    checks: DiscussionChecks;
}

export function ChecksBadge({ checks }: ChecksBadgeProps) {
    return checks.passed ? (
        <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-300">
            <CheckCircle2 className="w-3.5 h-3.5" />
            合格
        </span>
    ) : (
        <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300">
            <TriangleAlert className="w-3.5 h-3.5" />
            要再生成
        </span>
    );
}

// ---------------------------------------------------------------------------
// ScriptExportButtons（コピー / Markdown ダウンロード）
// ---------------------------------------------------------------------------

interface ScriptExportButtonsProps {
    bookName: string;
    turns: DiscussionTurn[];
    segments?: Record<string, string> | null;
    createdAt?: string | null;
}

const EXPORT_BUTTON_CLASS =
    'inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors';

export function ScriptExportButtons({
    bookName,
    turns,
    segments,
    createdAt,
}: ScriptExportButtonsProps) {
    const buildMarkdown = () => buildScriptMarkdown(bookName, turns, segments ?? {}, createdAt);

    const handleCopy = async () => {
        try {
            await navigator.clipboard.writeText(buildMarkdown());
            toast.success('台本をクリップボードにコピーしました');
        } catch {
            toast.error('クリップボードへのコピーに失敗しました');
        }
    };

    const handleDownload = () => {
        downloadScriptMarkdown(bookName, buildMarkdown());
    };

    return (
        <div className="flex items-center gap-2">
            <button type="button" onClick={() => void handleCopy()} className={EXPORT_BUTTON_CLASS}>
                <Copy className="w-3.5 h-3.5" />
                コピー
            </button>
            <button type="button" onClick={handleDownload} className={EXPORT_BUTTON_CLASS}>
                <Download className="w-3.5 h-3.5" />
                MD ダウンロード
            </button>
        </div>
    );
}
