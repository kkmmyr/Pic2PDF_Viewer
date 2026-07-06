/**
 * 読書会 番組台本のエクスポートユーティリティ（B-28）。
 *
 * ホストキャラはサーバー側でレイ（A）＆ミオ（B）固定のため、
 * 表示名のマッピングもここで一元管理する。
 */
import type { DiscussionTurn } from './types';

/** 話者 id → 表示名の固定マップ。A=レイ / B=ミオ。 */
export const SPEAKER_NAMES: Record<'A' | 'B', string> = {
    A: 'レイ',
    B: 'ミオ',
};

/** 話者 id を表示名に変換する。未知の id はそのまま返す。 */
export function speakerName(speaker: string): string {
    return speaker === 'A' || speaker === 'B' ? SPEAKER_NAMES[speaker] : speaker;
}

/**
 * 台本を Markdown 文字列に変換する。
 *
 * - 先頭: `# 『{bookName}』番組台本`（createdAt があれば生成日時行を追加）
 * - turn.segment が切り替わるごとに `## {セグメント見出し}` を挿入
 * - 各発言は `**レイ**: text` 形式
 * - v1 データ（segment なし）は見出しなしのフラット出力
 */
export function buildScriptMarkdown(
    bookName: string,
    turns: DiscussionTurn[],
    segments: Record<string, string>,
    createdAt?: string | null,
): string {
    const lines: string[] = [`# 『${bookName}』番組台本`];
    if (createdAt) {
        lines.push('', `生成日時: ${createdAt}`);
    }
    let prevSegment: string | undefined;
    for (const turn of turns) {
        if (turn.segment && turn.segment !== prevSegment) {
            lines.push('', `## ${segments[turn.segment] ?? turn.segment}`);
            prevSegment = turn.segment;
        }
        lines.push('', `**${speakerName(turn.speaker)}**: ${turn.text}`);
    }
    return `${lines.join('\n')}\n`;
}

/** `{book}_台本_{ts}.md` 用のタイムスタンプ（YYYYMMDD_HHmmss）。 */
function formatTimestamp(d: Date): string {
    const pad = (n: number) => String(n).padStart(2, '0');
    return (
        `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}` +
        `_${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`
    );
}

/** Markdown 文字列を `{book}_台本_{ts}.md` としてダウンロードさせる。 */
export function downloadScriptMarkdown(bookName: string, markdown: string): void {
    const blob = new Blob([markdown], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${bookName}_台本_${formatTimestamp(new Date())}.md`;
    a.click();
    URL.revokeObjectURL(url);
}
