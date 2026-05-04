import { useEffect, RefObject } from 'react';

interface Options {
    /** focus を発火するまでの遅延 (ms)。Dialog のオープン直後は要素がまだ DOM に乗っていないことがあるため、Dialog 用途では 50 程度を推奨。デフォルト 0。 */
    delay?: number;
    /** focus 後に select() も呼ぶか（input の中身を全選択して上書き入力しやすくする）。デフォルト false。 */
    select?: boolean;
}

/**
 * `shouldFocus` が `true` に切り替わったタイミングで `ref` の要素を `focus()` する共通フック。
 *
 * 旧来は各 Dialog で `useEffect + setTimeout(0/50) + ref.current?.focus()` を再実装し、
 * `select()` の有無や遅延値（0 / 50）が不統一だった。これを集約することで Dialog 横断の
 * フォーカス挙動を 1 箇所で管理できるようにする。
 */
export function useAutoFocusInput<T extends HTMLElement>(
    ref: RefObject<T | null>,
    shouldFocus: boolean,
    options: Options = {},
) {
    const { delay = 0, select = false } = options;
    useEffect(() => {
        if (!shouldFocus) return;
        const timer = setTimeout(() => {
            const el = ref.current;
            if (!el) return;
            el.focus();
            if (select && typeof (el as unknown as HTMLInputElement).select === 'function') {
                (el as unknown as HTMLInputElement).select();
            }
        }, delay);
        return () => clearTimeout(timer);
    }, [shouldFocus, delay, select, ref]);
}
