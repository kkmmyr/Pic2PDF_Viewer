import { useCallback, useState } from 'react';

import type { BuildMode } from '@/features/novel_build/types';
import type { BookSummary } from '@/features/novel_db/types';

export interface BuildTargetState {
    all: boolean;
    setAll: (v: boolean) => void;
    selected: string;
    setSelected: (v: string) => void;
    showBuilt: boolean;
    handleShowBuiltChange: (v: boolean) => void;
    filtered: BookSummary[];
    handleEnqueue: () => void;
}

/**
 * Build / コンテキスト生成 / 関係グラフ生成の各モードで共通する
 * 「全冊 or 1 冊選択 + showBuilt フィルター + enqueue」状態を管理する。
 *
 * `useNovelManage` 内で 3 回呼び出すことで同型の state 管理重複を解消する。
 */
export function useBuildTarget(
    mode: BuildMode,
    books: BookSummary[],
    enqueue: (bookName: string | null, allBooks: boolean, mode: BuildMode) => Promise<void>,
): BuildTargetState {
    const [all, setAll] = useState(false);
    const [selected, setSelected] = useState('');
    const [showBuilt, setShowBuilt] = useState(false);

    const filtered = books.filter((b) =>
        showBuilt ? b.indexed_at !== null : b.indexed_at === null,
    );

    const handleShowBuiltChange = useCallback(
        (value: boolean) => {
            const next = books.filter((b) =>
                value ? b.indexed_at !== null : b.indexed_at === null,
            );
            setShowBuilt(value);
            setSelected(next.length > 0 ? next[0].name : '');
        },
        [books],
    );

    const handleEnqueue = useCallback(() => {
        if (all) {
            void enqueue(null, true, mode);
        } else {
            if (!selected) return;
            void enqueue(selected, false, mode);
        }
    }, [all, selected, mode, enqueue]);

    return {
        all,
        setAll,
        selected,
        setSelected,
        showBuilt,
        handleShowBuiltChange,
        filtered,
        handleEnqueue,
    };
}
