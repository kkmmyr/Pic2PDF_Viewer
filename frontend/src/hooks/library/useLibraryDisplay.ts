import { useMemo } from 'react';
import type { PdfFile, BookMetaMap } from '@/types';
import { useLibraryGrouping, type GroupMode, type GroupedLibrary } from './useLibraryGrouping';
import type { PinsMap } from './useLibraryPins';

type Crumb = { kind: 'home' | 'author' | 'series'; label: string; onClick?: () => void };

interface UseLibraryDisplayParams {
    filteredPdfs: PdfFile[];
    meta: BookMetaMap;
    currentPath: string;
    /** ユーザー選択の集約モード（`useLibrarySettings` の値） */
    groupMode: GroupMode;
    authorFilter: string;
    seriesFilter: string;
    /** シリーズドリルダウン中の `series_index` 順ソート用 */
    getSeries: (path: string, name: string) => { id: string; index: number; title: string } | null;
    /** breadcrumbs のホームクリック用（author / series を一括クリア） */
    clearAllDrilldown: () => void;
    /** breadcrumbs の作者階層クリック用（series のみクリア） */
    setSeriesFilter: (v: string) => void;
    /** シリーズ代表ピン（series_id → book_name） */
    seriesPins?: PinsMap;
    /** 作者代表ピン（author_key → book_name） */
    authorPins?: PinsMap;
}

interface UseLibraryDisplayResult {
    /** 階層構造を考慮した集約モード（`useLibraryGrouping` に渡す値） */
    effectiveGroupMode: GroupMode;
    grouped: GroupedLibrary;
    /** 表示順を確定させた最終リスト。シリーズドリルダウン中は `series_index` 昇順 */
    displayPdfs: PdfFile[];
    /** ドリルダウン階層のパンくず（authorFilter / seriesFilter どちらもなければ空配列） */
    breadcrumbs: Crumb[];
}

/**
 * ライブラリ表示の派生計算をまとめる。
 *
 * - `effectiveGroupMode`: ドリルダウン階層に応じてユーザー選択 mode を補正
 *     - シリーズ中はフラット強制
 *     - `author-then-series` は authorFilter の有無で 2 段階切替
 *     - 単純な author/series モードもドリルダウン中は集約解除
 * - `displayPdfs`: シリーズ中は DnD 並べ替え結果を即時反映するため `series_index` 昇順で並べ直す
 * - `breadcrumbs`: 「ライブラリ → 作者 → シリーズ」のクリック可能な階層
 */
export function useLibraryDisplay({
    filteredPdfs,
    meta,
    currentPath,
    groupMode,
    authorFilter,
    seriesFilter,
    getSeries,
    clearAllDrilldown,
    setSeriesFilter,
    seriesPins,
    authorPins,
}: UseLibraryDisplayParams): UseLibraryDisplayResult {
    const effectiveGroupMode: GroupMode = seriesFilter
        ? 'none'
        : groupMode === 'author-then-series'
          ? authorFilter
              ? 'series'
              : 'author'
          : authorFilter
            ? 'none'
            : groupMode;

    const grouped = useLibraryGrouping({
        pdfs: filteredPdfs,
        meta,
        currentPath,
        mode: effectiveGroupMode,
        seriesPins,
        authorPins,
    });

    const displayPdfs = useMemo(() => {
        if (!seriesFilter) return grouped.items;
        return [...grouped.items].sort((a, b) => {
            const ai = getSeries(currentPath, a.name)?.index ?? 0;
            const bi = getSeries(currentPath, b.name)?.index ?? 0;
            return ai - bi;
        });
    }, [seriesFilter, grouped.items, currentPath, getSeries]);

    const breadcrumbs = useMemo<Crumb[]>(() => {
        if (!authorFilter && !seriesFilter) return [];
        const seriesTitle = seriesFilter
            ? (Object.values(meta).find((e) => e.series_id === seriesFilter)?.series_title ??
              'シリーズ')
            : null;
        const items: Crumb[] = [{ kind: 'home', label: 'ライブラリ', onClick: clearAllDrilldown }];
        if (authorFilter) {
            items.push({
                kind: 'author',
                label: authorFilter,
                // 作者階層に戻る = seriesFilter のみクリア。現在地（series なし）ならクリック不可
                onClick: seriesFilter ? () => setSeriesFilter('') : undefined,
            });
        }
        if (seriesFilter) {
            items.push({ kind: 'series', label: seriesTitle ?? 'シリーズ' });
        }
        return items;
    }, [authorFilter, seriesFilter, meta, clearAllDrilldown, setSeriesFilter]);

    return { effectiveGroupMode, grouped, displayPdfs, breadcrumbs };
}
