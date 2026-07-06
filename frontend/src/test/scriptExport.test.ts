/**
 * script-export: buildScriptMarkdown / speakerName（B-28）。
 */
import { describe, it, expect } from 'vitest';

import { buildScriptMarkdown, speakerName, SPEAKER_NAMES } from '@/features/novel_db/script-export';
import type { DiscussionTurn } from '@/features/novel_db/types';

const SEGMENTS: Record<string, string> = {
    op_hook: 'OPフック',
    theme1: 'テーマ1',
};

const V2_TURNS: DiscussionTurn[] = [
    { speaker: 'A', text: 'つかみの一言', segment: 'op_hook' },
    { speaker: 'B', text: '受けの一言', segment: 'op_hook' },
    { speaker: 'A', text: '本題に入ります', segment: 'theme1' },
];

describe('speakerName', () => {
    it('A=レイ / B=ミオ に変換し、未知の id はそのまま返す', () => {
        expect(speakerName('A')).toBe('レイ');
        expect(speakerName('B')).toBe('ミオ');
        expect(speakerName('C')).toBe('C');
        expect(SPEAKER_NAMES).toEqual({ A: 'レイ', B: 'ミオ' });
    });
});

describe('buildScriptMarkdown', () => {
    it('セグメント見出し + 話者名変換つきの Markdown を生成する', () => {
        const md = buildScriptMarkdown('銀河鉄道の夜', V2_TURNS, SEGMENTS);
        expect(md).toBe(
            [
                '# 『銀河鉄道の夜』番組台本',
                '',
                '## OPフック',
                '',
                '**レイ**: つかみの一言',
                '',
                '**ミオ**: 受けの一言',
                '',
                '## テーマ1',
                '',
                '**レイ**: 本題に入ります',
                '',
            ].join('\n'),
        );
    });

    it('createdAt を渡すと生成日時行が入る', () => {
        const md = buildScriptMarkdown('本', V2_TURNS.slice(0, 1), SEGMENTS, '2026-07-07 10:00');
        expect(md).toContain('# 『本』番組台本');
        expect(md).toContain('生成日時: 2026-07-07 10:00');
    });

    it('v1 データ（segment なし）は見出しなしのフラット出力', () => {
        const v1Turns: DiscussionTurn[] = [
            { speaker: 'A', text: '一言目' },
            { speaker: 'B', text: '二言目' },
        ];
        const md = buildScriptMarkdown('旧作', v1Turns, {});
        expect(md).not.toContain('##');
        expect(md).toContain('**レイ**: 一言目');
        expect(md).toContain('**ミオ**: 二言目');
    });

    it('segments に見出しがない id はそのまま見出しに使う', () => {
        const md = buildScriptMarkdown(
            '本',
            [{ speaker: 'A', text: 'x', segment: 'unknown_seg' }],
            {},
        );
        expect(md).toContain('## unknown_seg');
    });

    it('同一セグメント連続では見出しを重複挿入しない', () => {
        const md = buildScriptMarkdown('本', V2_TURNS, SEGMENTS);
        expect(md.match(/## OPフック/g)).toHaveLength(1);
    });
});
