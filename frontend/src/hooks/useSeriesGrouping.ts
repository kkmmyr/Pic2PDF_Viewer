import { useMemo } from 'react';
import type { PdfFile, BookMetaMap } from '../types';

export interface SeriesGroup {
    /** 代表として表示する PdfFile（series_index が最大のもの） */
    representative: PdfFile;
    /** シリーズ全巻のリスト（series_index 昇順） */
    members: PdfFile[];
    seriesId: string;
    seriesTitle: string;
}

export interface GroupedLibrary {
    /** シリーズ単位でまとめた表示順の書籍リスト（代表 + 単独本） */
    items: PdfFile[];
    /** 代表書籍 name → 関連グループ。単独本は含まれない */
    seriesByRepresentativeName: Map<string, SeriesGroup>;
    /** 代表書籍 name → シリーズメンバー数（バッジ表示用） */
    memberCountByRepresentativeName: Map<string, number>;
}

interface UseSeriesGroupingParams {
    pdfs: PdfFile[];
    meta: BookMetaMap;
    currentPath: string;
    enabled: boolean;
}

function metaKey(path: string, name: string): string {
    return path ? `${path}/${name}` : name;
}

/**
 * 書籍リストをシリーズ単位でグループ化する。
 *
 * `enabled=false` のときは入力 `pdfs` をそのまま返す（フラット表示）。
 * `enabled=true` のときは:
 *   - 同 `series_id` の書籍は最大 `series_index` を代表として 1 枚に集約
 *   - シリーズに属さない書籍はそのまま並ぶ
 *   - 元の `pdfs` の順序を可能な限り保つ（シリーズの表示位置は代表書籍の元位置）
 */
export function useSeriesGrouping({
    pdfs, meta, currentPath, enabled,
}: UseSeriesGroupingParams): GroupedLibrary {
    return useMemo(() => {
        if (!enabled) {
            return {
                items: pdfs,
                seriesByRepresentativeName: new Map(),
                memberCountByRepresentativeName: new Map(),
            };
        }

        // series_id ごとにメンバーを集計
        const buckets = new Map<string, PdfFile[]>();
        const standalone: PdfFile[] = [];
        for (const pdf of pdfs) {
            const entry = meta[metaKey(currentPath, pdf.name)];
            const sid = entry?.series_id;
            if (!sid) {
                standalone.push(pdf);
                continue;
            }
            const arr = buckets.get(sid) ?? [];
            arr.push(pdf);
            buckets.set(sid, arr);
        }

        // 各シリーズの代表（最大 index）を選ぶ + members を index 昇順にソート
        const representatives = new Map<string, PdfFile>();   // series_id -> 代表 PdfFile
        const seriesByRepresentativeName = new Map<string, SeriesGroup>();
        const memberCountByRepresentativeName = new Map<string, number>();

        for (const [sid, members] of buckets) {
            const entries = members.map(p => {
                const e = meta[metaKey(currentPath, p.name)];
                return { pdf: p, index: e?.series_index ?? 0, title: e?.series_title ?? '' };
            });
            entries.sort((a, b) => a.index - b.index);
            const rep = entries[entries.length - 1].pdf;  // 最大 index
            const sortedMembers = entries.map(x => x.pdf);
            const seriesTitle = entries.find(x => x.title)?.title ?? '';

            representatives.set(sid, rep);
            seriesByRepresentativeName.set(rep.name, {
                representative: rep,
                members: sortedMembers,
                seriesId: sid,
                seriesTitle,
            });
            memberCountByRepresentativeName.set(rep.name, sortedMembers.length);
        }

        // 元 pdfs の順序を保ちつつ、シリーズメンバー2冊目以降を間引く
        const seenSeries = new Set<string>();
        const items: PdfFile[] = [];
        for (const pdf of pdfs) {
            const entry = meta[metaKey(currentPath, pdf.name)];
            const sid = entry?.series_id;
            if (!sid) {
                items.push(pdf);
                continue;
            }
            if (seenSeries.has(sid)) continue;
            seenSeries.add(sid);
            // 代表で表示
            items.push(representatives.get(sid) ?? pdf);
        }

        // standalone はそのまま items に既に含まれているので追加処理不要
        // （上のループで sid 無しは items に追加済み）
        void standalone;

        return { items, seriesByRepresentativeName, memberCountByRepresentativeName };
    }, [pdfs, meta, currentPath, enabled]);
}
