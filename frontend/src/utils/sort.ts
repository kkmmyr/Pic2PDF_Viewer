export const cmpJa = (a: string, b: string): number => a.localeCompare(b, 'ja');

/**
 * 複数の要素を一括で移動するヘルパー。AT セマンティクス（active アイテムが
 * 結果配列の `targetIndex` に着地）。
 *
 * - `movedIndices` が指す要素を `arr` から取り除き、元の相対順を保ったまま
 *   `activeIndex` のアイテムが結果配列の `targetIndex` に来るように一括挿入する
 * - `arrayMove` と整合する設計: 単一要素 (`movedIndices=[activeIndex]`) のときは
 *   `arrayMove(arr, activeIndex, targetIndex)` と等価
 * - `targetIndex` が `movedIndices` に含まれる場合は何もしない（自分の上にドロップ）
 *
 * 例 1（単独）: arr=[A,B,C,D,E], movedIndices=[1], activeIndex=1, targetIndex=3
 *   → 結果 [A,C,D,B,E]（B が D のあった位置 = idx 3 に着地、arrayMove と同じ）
 *
 * 例 2（グループ active=A）: arr=[A,B,C,D,E], movedIndices=[0,2], activeIndex=0, targetIndex=4
 *   → 結果 [B,D,E,A,C]（A を idx 4 に置きたいが C も入れるためクランプ → A=3, C=4）
 *
 * 例 3（グループ active=C）: arr=[A,B,C,D,E], movedIndices=[0,2], activeIndex=2, targetIndex=4
 *   → 結果 [B,D,E,A,C]（C を idx 4 に置く、A は C の直前で idx 3）
 */
export function moveMultipleByIndex<T>(
    arr: T[],
    movedIndices: number[],
    activeIndex: number,
    targetIndex: number,
): T[] {
    if (movedIndices.length === 0) return arr.slice();
    const movedSet = new Set(movedIndices);
    if (movedSet.has(targetIndex)) return arr.slice();

    const sortedMoved = [...movedIndices].sort((a, b) => a - b);
    const moved = sortedMoved.map((i) => arr[i]);
    const remaining = arr.filter((_, i) => !movedSet.has(i));

    // active アイテムを結果配列の targetIndex に置きたいので、グループの先頭が
    // 来るべき位置を逆算する。clamp で remaining の範囲内に収める。
    const activeOffsetInMoved = sortedMoved.indexOf(activeIndex);
    const desiredGroupStart = targetIndex - activeOffsetInMoved;
    const insertPos = Math.max(0, Math.min(remaining.length, desiredGroupStart));

    return [...remaining.slice(0, insertPos), ...moved, ...remaining.slice(insertPos)];
}
