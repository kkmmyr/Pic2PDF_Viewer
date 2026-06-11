import { renderHook } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { useNextSeriesVolume, usePrevSeriesVolume } from '@/hooks/reader/useNextSeriesVolume';
import type { BookMetaMap } from '@/types';

type SeriesRef = { id: string; title: string; index: number } | null;

const META: BookMetaMap = {
    'vol1.pdf': { series_id: 's1', series_title: 'テスト', series_index: 1 },
    'vol2.pdf': { series_id: 's1', series_title: 'テスト', series_index: 2 },
    'vol3.pdf': { series_id: 's1', series_title: 'テスト', series_index: 3 },
    'other.pdf': { series_id: 's2', series_title: '別シリーズ', series_index: 1 },
    'sub/vol1.pdf': { series_id: 's3', series_title: 'サブ', series_index: 1 },
    'sub/vol2.pdf': { series_id: 's3', series_title: 'サブ', series_index: 2 },
};

const getSeries = (path: string, name: string): SeriesRef => {
    const key = path ? `${path}/${name}` : name;
    const e = META[key];
    if (!e?.series_id || e.series_index === undefined) return null;
    return { id: e.series_id, title: e.series_title ?? '', index: e.series_index };
};

describe('useNextSeriesVolume', () => {
    it('vol1 から次は vol2', () => {
        const { result } = renderHook(() => useNextSeriesVolume(META, getSeries, '', 'vol1.pdf'));
        expect(result.current?.name).toBe('vol2.pdf');
        expect(result.current?.index).toBe(2);
    });

    it('vol2 から次は vol3（最小の index で +1）', () => {
        const { result } = renderHook(() => useNextSeriesVolume(META, getSeries, '', 'vol2.pdf'));
        expect(result.current?.name).toBe('vol3.pdf');
    });

    it('最終巻 vol3 では次巻なし（null）', () => {
        const { result } = renderHook(() => useNextSeriesVolume(META, getSeries, '', 'vol3.pdf'));
        expect(result.current).toBeNull();
    });

    it('シリーズに属さない書籍では null', () => {
        const { result } = renderHook(() =>
            useNextSeriesVolume(META, getSeries, '', 'unknown.pdf'),
        );
        expect(result.current).toBeNull();
    });

    it('サブフォルダ内のシリーズも辿れる（同フォルダ判定）', () => {
        const { result } = renderHook(() =>
            useNextSeriesVolume(META, getSeries, 'sub', 'vol1.pdf'),
        );
        expect(result.current?.name).toBe('vol2.pdf');
    });

    it('別フォルダの同シリーズは対象外（サブで vol1 → 親フォルダの vol2 を選ばない）', () => {
        // META には 'vol2.pdf' (s1) と 'sub/vol2.pdf' (s3) がある
        // sub/vol1 の series_id=s3。currentPath='sub' で同フォルダ縛り → 'sub/vol2.pdf' を選ぶ
        const { result } = renderHook(() =>
            useNextSeriesVolume(META, getSeries, 'sub', 'vol1.pdf'),
        );
        expect(result.current?.name).toBe('vol2.pdf'); // 'sub/vol2.pdf' の rest 部分
    });

    it('series_index が飛び飛びでも次のものを選ぶ（最小の大きい index）', () => {
        const meta: BookMetaMap = {
            'a.pdf': { series_id: 's', series_index: 1 },
            'b.pdf': { series_id: 's', series_index: 5 },
            'c.pdf': { series_id: 's', series_index: 10 },
        };
        const gs = (_path: string, name: string): SeriesRef => {
            const e = meta[name];
            if (!e?.series_id || e.series_index === undefined) return null;
            return { id: e.series_id, title: '', index: e.series_index };
        };

        const { result } = renderHook(() => useNextSeriesVolume(meta, gs, '', 'a.pdf'));
        expect(result.current?.index).toBe(5); // 1 → 5（10 ではない）
    });
});

describe('usePrevSeriesVolume', () => {
    it('vol2 から前は vol1', () => {
        const { result } = renderHook(() => usePrevSeriesVolume(META, getSeries, '', 'vol2.pdf'));
        expect(result.current?.name).toBe('vol1.pdf');
    });

    it('vol3 から前は vol2（最大の index で -1）', () => {
        const { result } = renderHook(() => usePrevSeriesVolume(META, getSeries, '', 'vol3.pdf'));
        expect(result.current?.name).toBe('vol2.pdf');
    });

    it('最初の巻 vol1 では前巻なし（null）', () => {
        const { result } = renderHook(() => usePrevSeriesVolume(META, getSeries, '', 'vol1.pdf'));
        expect(result.current).toBeNull();
    });

    it('シリーズ未所属で null', () => {
        const { result } = renderHook(() =>
            usePrevSeriesVolume(META, getSeries, '', 'unknown.pdf'),
        );
        expect(result.current).toBeNull();
    });

    it('飛び飛びの index で前のものを選ぶ（最大の小さい index）', () => {
        const meta: BookMetaMap = {
            'a.pdf': { series_id: 's', series_index: 1 },
            'b.pdf': { series_id: 's', series_index: 5 },
            'c.pdf': { series_id: 's', series_index: 10 },
        };
        const gs = (_path: string, name: string): SeriesRef => {
            const e = meta[name];
            if (!e?.series_id || e.series_index === undefined) return null;
            return { id: e.series_id, title: '', index: e.series_index };
        };

        const { result } = renderHook(() => usePrevSeriesVolume(meta, gs, '', 'c.pdf'));
        expect(result.current?.index).toBe(5); // 10 → 5（1 ではない）
    });
});
