import { useCallback } from 'react';
import { toast } from 'sonner';
import { errorMessage } from '../utils/error';

/**
 * 非同期処理の例外を catch して sonner エラートーストに流すヘルパーフック。
 *
 *     await runAsync(() => someAsync(), 'XXX に失敗しました。');
 *
 * `fallback` には固定文字列または `(e) => string` の関数を指定できる。
 * 例外を握りつぶして `undefined` を返す。`rethrow: true` で再 throw。
 */
export function useAsyncToast() {
    return useCallback(
        async <T>(
            fn: () => Promise<T>,
            fallback: string | ((e: unknown) => string),
            options?: { rethrow?: boolean },
        ): Promise<T | undefined> => {
            try {
                return await fn();
            } catch (e: unknown) {
                const message =
                    typeof fallback === 'function' ? fallback(e) : errorMessage(e, fallback);
                toast.error(message);
                if (options?.rethrow) throw e;
                return undefined;
            }
        },
        [],
    );
}
