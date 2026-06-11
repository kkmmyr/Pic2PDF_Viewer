/**
 * 質問入力欄。文字数カウンタ + 送信ボタン + 連投警告。
 */
import { useState } from 'react';
import { Send } from 'lucide-react';

import { NOVEL_DB_CONFIG } from '@/constants';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';

interface Props {
    onSubmit: (question: string) => void;
    disabled?: boolean;
    isReplay: (q: string) => boolean;
}

export default function QuestionInput({ onSubmit, disabled, isReplay }: Props) {
    const [text, setText] = useState('');
    const [confirmingReplay, setConfirmingReplay] = useState(false);

    const len = text.length;
    const max = NOVEL_DB_CONFIG.QUESTION_MAX_LENGTH;
    const overLimit = len > max;
    const trimmed = text.trim();

    const handleSubmit = () => {
        if (!trimmed || overLimit || disabled) return;
        if (isReplay(trimmed)) {
            setConfirmingReplay(true);
            return;
        }
        onSubmit(trimmed);
        setText('');
    };

    const handleConfirmReplay = () => {
        setConfirmingReplay(false);
        onSubmit(trimmed);
        setText('');
    };

    return (
        <>
            <div className="space-y-2">
                <textarea
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                    placeholder="質問を入力…（例: デュークはどんな人物?）"
                    disabled={disabled}
                    rows={4}
                    className="w-full p-3 text-sm rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50 resize-y"
                />
                <div className="flex items-center justify-between">
                    <span
                        className={`text-xs ${overLimit ? 'text-red-600 dark:text-red-400' : 'text-gray-500 dark:text-gray-400'}`}
                    >
                        {len} / {max}
                    </span>
                    <button
                        onClick={handleSubmit}
                        disabled={!trimmed || overLimit || disabled}
                        className="px-4 py-1.5 text-sm rounded-md bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5"
                    >
                        <Send className="w-4 h-4" />
                        送信
                    </button>
                </div>
            </div>
            <ConfirmDialog
                open={confirmingReplay}
                title="同じ質問を再送しますか?"
                message="直前と完全に一致する質問です。同じ内容で再度問い合わせる場合は「送信」を押してください。"
                confirmLabel="送信"
                onConfirm={handleConfirmReplay}
                onCancel={() => setConfirmingReplay(false)}
            />
        </>
    );
}
