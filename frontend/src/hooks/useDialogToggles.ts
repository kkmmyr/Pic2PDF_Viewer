import { useState, useCallback } from 'react';

/**
 * 同じ文脈で複数のダイアログを排他的に開閉するためのトグルフック。
 *
 * `useState<boolean>(false)` を 5 つ並べる代わりに 1 つの `K | null` で管理し、
 * `isOpen('foo')` / `open('foo')` / `close()` のシンプルな API を提供する。
 *
 * 排他制御（同時に複数のダイアログが開かない）が暗黙の仕様になる点に注意。
 */
export function useDialogToggles<K extends string>() {
    const [active, setActive] = useState<K | null>(null);

    const isOpen = useCallback((key: K) => active === key, [active]);
    const open = useCallback((key: K) => setActive(key), []);
    const close = useCallback(() => setActive(null), []);

    return { isOpen, open, close };
}
