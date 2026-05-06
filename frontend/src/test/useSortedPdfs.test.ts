/**
 * useSortedPdfs フックのユニットテスト。
 *
 * 実行方法:
 *   cd frontend && npx vitest run
 */
import { renderHook } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { useSortedPdfs } from '../hooks/useSortedPdfs';
import type { PdfFile, SortOrder } from '../types';

const pdf = (name: string, created_at = 0): PdfFile => ({ name, thumbnail: null, created_at });

function sortedNames(
    pdfs: PdfFile[],
    sortOrder: SortOrder,
    favorites: Set<string> = new Set(),
    getViewCount?: (name: string) => number,
    getLastViewedAt?: (name: string) => number | undefined,
): string[] {
    const { result } = renderHook(() =>
        useSortedPdfs(pdfs, sortOrder, favorites, getViewCount, getLastViewedAt),
    );
    return result.current.map((p) => p.name);
}

describe('useSortedPdfs', () => {
    describe('name_asc / name_desc', () => {
        it('名前昇順で並ぶ', () => {
            const pdfs = [pdf('Charlie'), pdf('Alpha'), pdf('Bravo')];
            expect(sortedNames(pdfs, 'name_asc')).toEqual(['Alpha', 'Bravo', 'Charlie']);
        });

        it('名前降順で並ぶ', () => {
            const pdfs = [pdf('Alpha'), pdf('Charlie'), pdf('Bravo')];
            expect(sortedNames(pdfs, 'name_desc')).toEqual(['Charlie', 'Bravo', 'Alpha']);
        });
    });

    describe('date_asc / date_desc', () => {
        it('作成日昇順で並ぶ', () => {
            const pdfs = [pdf('a', 300), pdf('b', 100), pdf('c', 200)];
            expect(sortedNames(pdfs, 'date_asc')).toEqual(['b', 'c', 'a']);
        });

        it('作成日降順で並ぶ', () => {
            const pdfs = [pdf('a', 100), pdf('b', 300), pdf('c', 200)];
            expect(sortedNames(pdfs, 'date_desc')).toEqual(['b', 'c', 'a']);
        });
    });

    describe('favorites_first', () => {
        it('お気に入りを先頭に、それ以外は名前昇順', () => {
            const pdfs = [pdf('Charlie'), pdf('Alpha'), pdf('Bravo'), pdf('Delta')];
            const favorites = new Set(['Bravo', 'Delta']);
            expect(sortedNames(pdfs, 'favorites_first', favorites)).toEqual([
                'Bravo',
                'Delta',
                'Alpha',
                'Charlie',
            ]);
        });
    });

    describe('view_desc', () => {
        it('閲覧回数の降順、同数は名前昇順', () => {
            const pdfs = [pdf('a'), pdf('b'), pdf('c'), pdf('d')];
            const counts = new Map([
                ['a', 1],
                ['b', 5],
                ['c', 5],
                ['d', 0],
            ]);
            const getViewCount = (name: string) => counts.get(name) ?? 0;
            expect(sortedNames(pdfs, 'view_desc', new Set(), getViewCount)).toEqual([
                'b',
                'c',
                'a',
                'd',
            ]);
        });

        it('getViewCount 未指定なら全て 0 として名前昇順', () => {
            const pdfs = [pdf('Charlie'), pdf('Alpha'), pdf('Bravo')];
            expect(sortedNames(pdfs, 'view_desc')).toEqual(['Alpha', 'Bravo', 'Charlie']);
        });
    });

    describe('recent_view', () => {
        it('最終閲覧時刻の降順、未閲覧は末尾、同時刻は名前昇順', () => {
            const pdfs = [pdf('a'), pdf('b'), pdf('c'), pdf('d')];
            const times = new Map<string, number | undefined>([
                ['a', 100],
                ['b', 300],
                ['c', undefined], // 未閲覧
                ['d', 200],
            ]);
            const getLastViewedAt = (name: string) => times.get(name);
            expect(sortedNames(pdfs, 'recent_view', new Set(), undefined, getLastViewedAt)).toEqual(
                ['b', 'd', 'a', 'c'],
            );
        });

        it('全員未閲覧なら名前昇順', () => {
            const pdfs = [pdf('Charlie'), pdf('Alpha'), pdf('Bravo')];
            const getLastViewedAt = () => undefined;
            expect(sortedNames(pdfs, 'recent_view', new Set(), undefined, getLastViewedAt)).toEqual(
                ['Alpha', 'Bravo', 'Charlie'],
            );
        });

        it('同時刻は名前昇順で安定', () => {
            const pdfs = [pdf('Charlie'), pdf('Alpha'), pdf('Bravo')];
            const getLastViewedAt = () => 100;
            expect(sortedNames(pdfs, 'recent_view', new Set(), undefined, getLastViewedAt)).toEqual(
                ['Alpha', 'Bravo', 'Charlie'],
            );
        });
    });

    it('元配列を破壊的に変更しない', () => {
        const pdfs = [pdf('Charlie'), pdf('Alpha'), pdf('Bravo')];
        const originalNames = pdfs.map((p) => p.name);
        sortedNames(pdfs, 'name_asc');
        expect(pdfs.map((p) => p.name)).toEqual(originalNames);
    });
});
