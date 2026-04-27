import { Zap } from 'lucide-react';

interface CompressionOptionsProps {
    enabled: boolean;
    quality: number;
    onEnabledChange: (enabled: boolean) => void;
    onQualityChange: (quality: number) => void;
}

/**
 * PDF 圧縮版生成のオプション設定。
 * チェックボックスで圧縮版生成の有効/無効を切り替え、有効時のみ品質スライダーを表示する。
 */
export function CompressionOptions({ enabled, quality, onEnabledChange, onQualityChange }: CompressionOptionsProps) {
    return (
        <div className="p-4 bg-blue-50 dark:bg-blue-900/20 rounded-lg border border-blue-100 dark:border-blue-800 space-y-4">
            <div className="flex items-center gap-3">
                <input
                    type="checkbox"
                    id="generateCompressed"
                    checked={enabled}
                    onChange={(e) => onEnabledChange(e.target.checked)}
                    className="w-5 h-5 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                />
                <label htmlFor="generateCompressed" className="text-sm font-semibold text-gray-800 dark:text-gray-200 flex items-center gap-2 cursor-pointer">
                    <Zap size={16} className="text-amber-500 fill-amber-500" />
                    Generate Compressed Version (別途保存)
                </label>
            </div>

            {enabled && (
                <div className="pl-8 space-y-2">
                    <div className="flex justify-between text-sm text-gray-600 dark:text-gray-400">
                        <span>Compression Quality: {quality}</span>
                        <span className="text-xs">Lower is smaller but lower quality</span>
                    </div>
                    <input
                        type="range"
                        min="10"
                        max="95"
                        step="5"
                        value={quality}
                        onChange={(e) => onQualityChange(parseInt(e.target.value))}
                        className="w-full h-2 bg-blue-200 dark:bg-blue-800 rounded-lg appearance-none cursor-pointer accent-blue-600"
                    />
                </div>
            )}
        </div>
    );
}
