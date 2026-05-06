import { useMemo } from 'react';
import type { PdfFile, BookMetaMap } from '../types';
import type { PinsMap } from './useLibraryPins';

/**
 * ライブラリの集約モード:
 * - `none`: フラット表示
 * - `series`: シリーズ単位で集約
 * - `author`: 作者単位で集約
 * - `author-then-series`: 2 階層モード。`useLibraryGrouping` 自体は `'none' | 'series' | 'author'`
 *   しか受け取らないため、LibraryPanel 側で階層に応じて `effectiveGroupMode` に変換する。
 */
export type GroupMode = 'none' | 'series' | 'author' | 'author-then-series';

interface GroupBadge {
    /** バッジに表示するメンバー数 */
    count: number;
    /** 集約種別（カードの装飾切替用） */
    kind: 'series' | 'author';
    /** ドリルダウン時に使う ID（series_id または作者集合キー） */
    groupId: string;
    /** カードのタイトルとして表示する文字列 */
    displayTitle: string;
    /** シリーズ集約のみ: view_count > 0 の既読冊数 */
    readCount: number;
}

export interface GroupedLibrary {
    /** 集約後の書籍リスト（代表 + 単独本）。元の `pdfs` の順序を可能な限り保つ */
    items: PdfFile[];
    /** 代表書籍 name → バッジ情報。単独本は含まれない */
    badgeByRepresentativeName: Map<string, GroupBadge>;
    /** 代表書籍 name → メンバーリスト（モーダル展開用、内部ソート順） */
    membersByRepresentativeName: Map<string, PdfFile[]>;
}

interface UseLibraryGroupingParams {
    pdfs: PdfFile[];
    meta: BookMetaMap;
    currentPath: string;
    /** 'none' のときはフラット表示。`pdfs` をそのまま返す */
    mode: GroupMode;
    /** series_id → ピン済み book_name。指定があればその巻を代表にする */
    seriesPins?: PinsMap;
    /** 作者キー → ピン済み book_name */
    authorPins?: PinsMap;
}

function metaKey(path: string, name: string): string {
    return path ? `${path}/${name}` : name;
}

/**
 * 書籍リストをシリーズ単位 / 作者単位で集約する。
 *
 * - シリーズモード: 同 `series_id` の書籍を最終巻のサムネイルで集約。
 * - 作者モード: 同じ作者集合の書籍を集約。代表は **入力順の最初**（呼び出し側がソート済みなら「ソート 1 位」）。
 * - メンバーが 1 冊だけのグループは集約しない（単独本のまま）。
 */
export function useLibraryGrouping({
    pdfs,
    meta,
    currentPath,
    mode,
    seriesPins,
    authorPins,
}: UseLibraryGroupingParams): GroupedLibrary {
    return useMemo(() => {
        if (mode === 'none') {
            return {
                items: pdfs,
                badgeByRepresentativeName: new Map(),
                membersByRepresentativeName: new Map(),
            };
        }

        // バケット化: groupId -> 候補書籍リスト
        const buckets = new Map<string, PdfFile[]>();
        const groupTitles = new Map<string, string>(); // groupId -> displayTitle

        for (const pdf of pdfs) {
            const entry = meta[metaKey(currentPath, pdf.name)];
            if (!entry) continue;

            if (mode === 'series') {
                const sid = entry.series_id;
                if (!sid) continue;
                if (!groupTitles.has(sid)) {
                    groupTitles.set(sid, entry.series_title ?? '');
                }
                const arr = buckets.get(sid) ?? [];
                arr.push(pdf);
                buckets.set(sid, arr);
            } else {
                // mode === 'author'
                const authors = entry.authors ?? [];
                if (authors.length === 0) continue;
                // 作者集合をキーとして使う（順序非依存）
                const sortedAuthors = [...authors].sort();
                const groupId = sortedAuthors.join('\n');
                if (!groupTitles.has(groupId)) {
                    groupTitles.set(groupId, `${sortedAuthors.join(', ')} コレクション`);
                }
                const arr = buckets.get(groupId) ?? [];
                arr.push(pdf);
                buckets.set(groupId, arr);
            }
        }

        // 代表選び + メンバー整列
        const representatives = new Map<string, PdfFile>();
        const badgeByRepresentativeName = new Map<string, GroupBadge>();
        const membersByRepresentativeName = new Map<string, PdfFile[]>();

        for (const [groupId, members] of buckets) {
            // 1 冊だけの集約は意味がない（単独本扱い）
            if (members.length < 2) continue;

            let rep: PdfFile;
            let sortedMembers: PdfFile[];

            if (mode === 'series') {
                const entries = members.map((p) => {
                    const e = meta[metaKey(currentPath, p.name)];
                    return { pdf: p, index: e?.series_index ?? 0 };
                });
                entries.sort((a, b) => a.index - b.index);
                sortedMembers = entries.map((x) => x.pdf);
                // ピン済みの巻があればそれを代表に、なければ最終巻
                const pinnedName = seriesPins?.[groupId];
                const pinned = pinnedName ? sortedMembers.find((p) => p.name === pinnedName) : null;
                rep = pinned ?? entries[entries.length - 1].pdf;
            } else {
                // 作者モード: 入力 pdfs の順序を保つ → 「ソート 1 位」が代表
                sortedMembers = members;
                const pinnedName = authorPins?.[groupId];
                const pinned = pinnedName ? members.find((p) => p.name === pinnedName) : null;
                rep = pinned ?? members[0];
            }

            const readCount =
                mode === 'series'
                    ? members.filter(
                          (p) => (meta[metaKey(currentPath, p.name)]?.view_count ?? 0) > 0,
                      ).length
                    : 0;

            representatives.set(groupId, rep);
            badgeByRepresentativeName.set(rep.name, {
                count: members.length,
                kind: mode === 'series' ? 'series' : 'author',
                groupId,
                displayTitle: groupTitles.get(groupId) ?? '',
                readCount,
            });
            membersByRepresentativeName.set(rep.name, sortedMembers);
        }

        // 元 pdfs の順序を保ちつつ、メンバー 2 冊目以降を間引く
        const seenGroups = new Set<string>();
        const items: PdfFile[] = [];
        for (const pdf of pdfs) {
            const entry = meta[metaKey(currentPath, pdf.name)];

            // この書籍がどのグループに属するか
            let groupId: string | null = null;
            if (entry) {
                if (mode === 'series' && entry.series_id) {
                    groupId = entry.series_id;
                } else if (mode === 'author' && (entry.authors ?? []).length > 0) {
                    groupId = [...(entry.authors ?? [])].sort().join('\n');
                }
            }

            if (!groupId || !representatives.has(groupId)) {
                // 集約対象でない、または集約しなかった（単独）グループ → そのまま並べる
                items.push(pdf);
                continue;
            }

            if (seenGroups.has(groupId)) continue;
            seenGroups.add(groupId);
            items.push(representatives.get(groupId) ?? pdf);
        }

        return { items, badgeByRepresentativeName, membersByRepresentativeName };
    }, [pdfs, meta, currentPath, mode, seriesPins, authorPins]);
}
