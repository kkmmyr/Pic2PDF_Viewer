import { useState, useEffect } from 'react';

/**
 * 値のデバウンス（Phase 54-8）。
 *
 * 入力 `value` を `delayMs` ミリ秒だけ遅延させた値を返す。
 * `value` が短い間に連続変更された場合は、最後の変更から `delayMs` 経過後に
 * デバウンス後の値が更新される。
 *
 * 旧来は `useEffect + setTimeout + clearTimeout` の組を `PdfSearchBar` /
 * `PageSlider` でそれぞれ自前実装していた。
 */
export function useDebouncedValue<T>(value: T, delayMs: number): T {
    const [debounced, setDebounced] = useState(value);

    useEffect(() => {
        const id = setTimeout(() => setDebounced(value), delayMs);
        return () => clearTimeout(id);
    }, [value, delayMs]);

    return debounced;
}
