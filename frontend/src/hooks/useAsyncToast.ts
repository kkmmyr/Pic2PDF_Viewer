import { useCallback } from 'react';
import type { ToastType } from './useToast';
import { errorMessage } from '../utils/error';

/**
 * 非同期処理の例外を catch してトースト通知に流すヘルパーフック。
 *
 * 多くのハンドラで繰り返されていた以下のボイラープレートを 1 行に圧縮する:
 *
 *     try {
 *         await someAsync();
 *     } catch (e: unknown) {
 *         showToast(e instanceof Error ? e.message : 'XXX に失敗しました。', 'error');
 *     }
 *
 *     ↓
 *
 *     await runAsync(() => someAsync(), 'XXX に失敗しました。');
 *
 * `fallback` には固定文字列または `(e) => string` の関数を指定できる。
 * 関数版は「{操作名}に失敗しました: {内訳}」のように原因を組み立てたい場合に使う。
 *
 * 例外を吐かず（呼び出し元で握りつぶす想定）に `undefined` を返す。
 * 呼び出し元で例外を再 throw したい場合はオプション `rethrow: true` を渡す。
 */
export function useAsyncToast(showToast: (message: string, type?: ToastType) => void) {
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
                showToast(message, 'error');
                if (options?.rethrow) throw e;
                return undefined;
            }
        },
        [showToast],
    );
}
