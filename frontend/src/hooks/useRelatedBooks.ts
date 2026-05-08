import { useMemo } from 'react';
import type { BookMetaMap } from '../types';

export interface RelatedSeriesBook {
    name: string;
    seriesIndex: number;
    seriesTitle: string;
}

export interface RelatedBook {
    name: string;
}

export interface RelatedBooks {
    /** 同 series_id の他の巻（自分を除く）。series_index 昇順、最大 SERIES_LIMIT 件 */
    series: RelatedSeriesBook[];
    /** 同作者集合の他書籍（少なくとも 1 人共通）。最大 AUTHOR_LIMIT 件 */
    authors: RelatedBook[];
    /** 共通タグを持つ他書籍（タグ交差 ≧ 1）。最大 TAG_LIMIT 件 */
    tags: RelatedBook[];
}

const SERIES_LIMIT = 8;
const AUTHOR_LIMIT = 5;
const TAG_LIMIT = 5;

/**
 * meta のキー (`{path}/{name}` または `{name}`) から、現在のパスと同じフォルダの
 * 書籍ファイル名だけを抽出する。useNextSeriesVolume と同じ規則。
 *
 * 戻り値:
 *   - 同フォルダなら書籍名（"a.pdf"）を返す
 *   - 別フォルダ・サブフォルダなら null
 */
function extractSameFolderName(key: string, currentPath: string): string | null {
    if (currentPath) {
        const prefix = `${currentPath}/`;
        if (!key.startsWith(prefix)) return null;
        const rest = key.slice(prefix.length);
        return rest.includes('/') ? null : rest;
    }
    return key.includes('/') ? null : key;
}

function arraysHaveIntersection<T>(a: readonly T[], b: readonly T[]): boolean {
    if (a.length === 0 || b.length === 0) return false;
    const set = new Set(a);
    return b.some((x) => set.has(x));
}

/**
 * 現在の書籍に関連する他書籍を「同シリーズ / 同作者 / 共通タグ」の 3 セクションに分けて返す。
 *
 * 重複は左から優先：
 *   - 同シリーズに含まれる書籍は authors / tags に再掲しない
 *   - 同作者に含まれる書籍は tags に再掲しない
 */
export function useRelatedBooks(
    meta: BookMetaMap,
    currentPath: string,
    selectedPdf: string,
): RelatedBooks {
    return useMemo(() => {
        const selfKey = currentPath ? `${currentPath}/${selectedPdf}` : selectedPdf;
        const self = meta[selfKey];
        const selfSeriesId = self?.series_id;
        const selfAuthors = self?.authors ?? [];
        const selfTags = self?.tags ?? [];

        const series: RelatedSeriesBook[] = [];
        const authors: RelatedBook[] = [];
        const tags: RelatedBook[] = [];
        const consumed = new Set<string>([selectedPdf]);

        for (const [key, entry] of Object.entries(meta)) {
            const name = extractSameFolderName(key, currentPath);
            if (name === null || name === selectedPdf) continue;

            // 1. 同シリーズ
            if (selfSeriesId && entry.series_id === selfSeriesId) {
                series.push({
                    name,
                    seriesIndex: entry.series_index ?? 0,
                    seriesTitle: entry.series_title ?? '',
                });
                consumed.add(name);
                continue;
            }
            // 2. 同作者（少なくとも 1 人共通）
            if (
                selfAuthors.length > 0 &&
                arraysHaveIntersection(selfAuthors, entry.authors ?? [])
            ) {
                authors.push({ name });
                consumed.add(name);
                continue;
            }
            // 3. 共通タグ
            if (selfTags.length > 0 && arraysHaveIntersection(selfTags, entry.tags ?? [])) {
                if (consumed.has(name)) continue;
                tags.push({ name });
            }
        }

        series.sort((a, b) => a.seriesIndex - b.seriesIndex);
        return {
            series: series.slice(0, SERIES_LIMIT),
            authors: authors.slice(0, AUTHOR_LIMIT),
            tags: tags.slice(0, TAG_LIMIT),
        };
    }, [meta, currentPath, selectedPdf]);
}
