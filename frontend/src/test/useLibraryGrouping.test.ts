import { renderHook } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { useLibraryGrouping } from '../hooks/useLibraryGrouping';
import type { PdfFile, BookMetaMap } from '../types';

const pdf = (name: string): PdfFile => ({ name, thumbnail: null, created_at: 0 });

// シリーズ用メタ: vol1=index1, vol2=index2, vol3=index3
const seriesMeta: BookMetaMap = {
    'vol1.pdf': { series_id: 'sid-1', series_title: '鬼滅の刃', series_index: 1, view_count: 1 },
    'vol2.pdf': { series_id: 'sid-1', series_title: '鬼滅の刃', series_index: 2, view_count: 0 },
    'vol3.pdf': { series_id: 'sid-1', series_title: '鬼滅の刃', series_index: 3, view_count: 0 },
    'solo.pdf': {},
};

// 作者用メタ
const authorMeta: BookMetaMap = {
    'bookA.pdf': { authors: ['Author A'] },
    'bookB.pdf': { authors: ['Author A'] },
    'bookC.pdf': { authors: ['Author A'] },
    'other.pdf': { authors: ['Author B'] },
};

function grouped(
    pdfs: PdfFile[],
    meta: BookMetaMap,
    mode: 'series' | 'author' | 'none',
    seriesPins?: Record<string, string>,
    authorPins?: Record<string, string>,
) {
    const { result } = renderHook(() =>
        useLibraryGrouping({ pdfs, meta, currentPath: '', mode, seriesPins, authorPins })
    );
    return result.current;
}

describe('useLibraryGrouping', () => {
    describe('mode=none', () => {
        it('pdfs をそのまま返す', () => {
            const pdfs = [pdf('a.pdf'), pdf('b.pdf')];
            const g = grouped(pdfs, {}, 'none');
            expect(g.items.map(p => p.name)).toEqual(['a.pdf', 'b.pdf']);
            expect(g.badgeByRepresentativeName.size).toBe(0);
        });
    });

    describe('シリーズ集約', () => {
        const pdfs = [pdf('vol1.pdf'), pdf('vol2.pdf'), pdf('vol3.pdf'), pdf('solo.pdf')];

        it('デフォルトは最終巻（series_index 最大）が代表', () => {
            const g = grouped(pdfs, seriesMeta, 'series');
            expect(g.items.map(p => p.name)).toContain('vol3.pdf');
            expect(g.badgeByRepresentativeName.has('vol3.pdf')).toBe(true);
        });

        it('seriesPins で指定した巻が代表になる', () => {
            const g = grouped(pdfs, seriesMeta, 'series', { 'sid-1': 'vol1.pdf' });
            expect(g.badgeByRepresentativeName.has('vol1.pdf')).toBe(true);
            expect(g.badgeByRepresentativeName.has('vol3.pdf')).toBe(false);
        });

        it('seriesPins の指定が存在しない name のとき最終巻にフォールバックする', () => {
            const g = grouped(pdfs, seriesMeta, 'series', { 'sid-1': 'missing.pdf' });
            expect(g.badgeByRepresentativeName.has('vol3.pdf')).toBe(true);
        });

        it('バッジに count と readCount が正しく入る', () => {
            const g = grouped(pdfs, seriesMeta, 'series');
            const badge = g.badgeByRepresentativeName.get('vol3.pdf')!;
            expect(badge.count).toBe(3);
            expect(badge.readCount).toBe(1); // vol1 のみ view_count > 0
        });

        it('シリーズ未所属の本は集約されずそのまま残る', () => {
            const g = grouped(pdfs, seriesMeta, 'series');
            expect(g.items.map(p => p.name)).toContain('solo.pdf');
        });

        it('メンバーは series_index 昇順で membersByRepresentativeName に入る', () => {
            const g = grouped(pdfs, seriesMeta, 'series');
            const rep = [...g.badgeByRepresentativeName.keys()][0];
            const members = g.membersByRepresentativeName.get(rep)!;
            const indices = members.map(p => seriesMeta[p.name]?.series_index ?? 0);
            expect(indices).toEqual([...indices].sort((a, b) => a - b));
        });
    });

    describe('作者集約', () => {
        const pdfs = [pdf('bookA.pdf'), pdf('bookB.pdf'), pdf('bookC.pdf'), pdf('other.pdf')];

        it('デフォルトは入力順先頭が代表', () => {
            const g = grouped(pdfs, authorMeta, 'author');
            expect(g.badgeByRepresentativeName.has('bookA.pdf')).toBe(true);
        });

        it('authorPins で指定した本が代表になる', () => {
            const g = grouped(pdfs, authorMeta, 'author', undefined, { 'Author A': 'bookC.pdf' });
            expect(g.badgeByRepresentativeName.has('bookC.pdf')).toBe(true);
            expect(g.badgeByRepresentativeName.has('bookA.pdf')).toBe(false);
        });

        it('authorPins の指定が存在しない name のとき先頭にフォールバックする', () => {
            const g = grouped(pdfs, authorMeta, 'author', undefined, { 'Author A': 'missing.pdf' });
            expect(g.badgeByRepresentativeName.has('bookA.pdf')).toBe(true);
        });

        it('作者キーは複数作者をソートして結合する（順序非依存）', () => {
            const meta: BookMetaMap = {
                'x.pdf': { authors: ['B', 'A'] },
                'y.pdf': { authors: ['A', 'B'] },
                'z.pdf': { authors: ['A', 'B'] },
            };
            const g = grouped([pdf('x.pdf'), pdf('y.pdf'), pdf('z.pdf')], meta, 'author');
            // 3冊とも同じグループに集約される
            const badge = [...g.badgeByRepresentativeName.values()][0];
            expect(badge.count).toBe(3);
        });

        it('1冊だけのグループは集約しない（単独本扱い）', () => {
            const g = grouped(pdfs, authorMeta, 'author');
            // Author B は 1 冊なのでバッジなし
            expect(g.badgeByRepresentativeName.has('other.pdf')).toBe(false);
            expect(g.items.map(p => p.name)).toContain('other.pdf');
        });
    });

    describe('ピンの独立性', () => {
        it('seriesPins は作者集約に影響しない', () => {
            const pdfs = [pdf('bookA.pdf'), pdf('bookB.pdf'), pdf('bookC.pdf')];
            const g = grouped(pdfs, authorMeta, 'author', { 'sid-x': 'vol1.pdf' });
            // デフォルト（先頭）が代表のまま
            expect(g.badgeByRepresentativeName.has('bookA.pdf')).toBe(true);
        });

        it('authorPins はシリーズ集約に影響しない', () => {
            const pdfs = [pdf('vol1.pdf'), pdf('vol2.pdf'), pdf('vol3.pdf')];
            const g = grouped(pdfs, seriesMeta, 'series', undefined, { 'Author A': 'bookA.pdf' });
            // デフォルト（最終巻）が代表のまま
            expect(g.badgeByRepresentativeName.has('vol3.pdf')).toBe(true);
        });
    });
});
