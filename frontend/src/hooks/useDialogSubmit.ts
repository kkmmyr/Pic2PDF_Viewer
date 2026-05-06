import { useState, useCallback } from 'react';
import { errorMessage } from '../utils/error';

/**
 * ダイアログの saving / error 状態と非同期送信ハンドラを共通化するフック。
 * バリデーションは呼び出し側で行い、通過後に handleSubmit(action) を呼ぶ。
 * action が throw した場合はエラーメッセージを error にセットする。
 */
export function useDialogSubmit(onClose: () => void, fallbackErrorMsg = '保存に失敗しました。') {
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const handleSubmit = useCallback(
        async (action: () => Promise<void>) => {
            setError(null);
            setSaving(true);
            try {
                await action();
                onClose();
            } catch (e: unknown) {
                setError(errorMessage(e, fallbackErrorMsg));
            } finally {
                setSaving(false);
            }
        },
        [onClose, fallbackErrorMsg],
    );

    return { saving, error, setError, handleSubmit };
}
