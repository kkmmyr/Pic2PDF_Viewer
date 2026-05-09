export const cmpJa = (a: string, b: string): number => a.localeCompare(b, 'ja');

/**
 * 複数の要素を一括で `targetIndex` の位置に挿入する。
 *
 * - `movedIndices` が指す要素を `arr` から取り除き、元の相対順を保ったまま
 *   `targetIndex`（移動前の index 基準）の直前に挿入する
 * - `targetIndex` が `movedIndices` に含まれる場合は何もしない（自分の上にドロップ）
 *
 * 例: arr=[A,B,C,D,E], movedIndices=[0,2], targetIndex=4
 *   → 結果 [B,D,A,C,E]（A と C は元の相対順を保ったまま、E の直前に挿入）
 *
 * 単独移動には @dnd-kit/sortable の `arrayMove` を使う。本関数はグループ DnD 用。
 */
export function moveMultipleByIndex<T>(
    arr: T[],
    movedIndices: number[],
    targetIndex: number,
): T[] {
    if (movedIndices.length === 0) return arr.slice();
    const movedSet = new Set(movedIndices);
    if (movedSet.has(targetIndex)) return arr.slice();

    const sortedMoved = [...movedIndices].sort((a, b) => a - b);
    const moved = sortedMoved.map((i) => arr[i]);
    const remaining = arr.filter((_, i) => !movedSet.has(i));

    // movedIndices のうち targetIndex より前にあったものの数だけ
    // remaining 側の挿入位置を前にずらす
    const removedBefore = sortedMoved.filter((i) => i < targetIndex).length;
    const adjustedTarget = Math.max(0, targetIndex - removedBefore);

    return [
        ...remaining.slice(0, adjustedTarget),
        ...moved,
        ...remaining.slice(adjustedTarget),
    ];
}
