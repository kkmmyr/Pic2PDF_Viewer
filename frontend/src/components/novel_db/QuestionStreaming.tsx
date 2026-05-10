/**
 * 質問送信中のストリーミング表示 + 停止ボタン。
 */
import { Loader2, Square } from 'lucide-react';

interface Props {
    text: string;
    onStop: () => void;
}

export default function QuestionStreaming({ text, onStop }: Props) {
    return (
        <div className="border border-primary-300 dark:border-primary-700 rounded-md p-4 bg-primary-50/40 dark:bg-primary-900/20 space-y-2">
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-sm text-primary-800 dark:text-primary-200">
                    <Loader2 className="w-4 h-4 animate-spin" />
                    回答生成中…
                </div>
                <button
                    onClick={onStop}
                    className="px-3 py-1 text-xs rounded-md bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-200 flex items-center gap-1"
                >
                    <Square className="w-3 h-3" />
                    停止
                </button>
            </div>
            <div className="text-sm text-gray-800 dark:text-gray-200 whitespace-pre-wrap leading-relaxed min-h-[3rem]">
                {text || <span className="text-gray-400">（モデル応答待ち…）</span>}
            </div>
        </div>
    );
}
