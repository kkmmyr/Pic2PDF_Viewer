import { Pencil, RefreshCw, EyeOff, Eye, BookCopy, BookOpen, Check } from 'lucide-react';
import type { ReadState } from '@/types';

const BTN_ICON =
    'p-0.5 rounded hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-300 dark:text-gray-600 hover:text-gray-500 dark:hover:text-gray-400 transition-colors';
const BTN_ICON_SERIES =
    'p-0.5 rounded hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-300 dark:text-gray-600 hover:text-accent-500 dark:hover:text-accent-400 transition-colors';

interface PdfCardActionButtonsProps {
    name: string;
    isSelectionMode: boolean;
    showHidden: boolean;
    isGroup: boolean;
    readState?: ReadState;
    onRename?: (name: string) => void;
    onRegenThumb?: (name: string) => void;
    onToggleHidden?: (name: string) => void;
    onEditSeries?: (name: string) => void;
}

function ReadStateBadge({ state }: { state: ReadState }) {
    if (state === 'unread') {
        return (
            <span
                className="px-1.5 py-0.5 rounded-full bg-sky-500 text-white text-xs font-semibold leading-none"
                title="未読"
            >
                NEW
            </span>
        );
    }
    if (state === 'reading') {
        return (
            <span
                className="px-1.5 py-0.5 rounded-full bg-accent-500 text-white text-xs font-semibold leading-none flex items-center"
                title="読書中"
                aria-label="読書中"
            >
                <BookOpen className="w-3 h-3" />
            </span>
        );
    }
    // done
    return (
        <span
            className="px-1.5 py-0.5 rounded-full bg-emerald-500 text-white text-xs font-semibold leading-none flex items-center"
            title="読了"
            aria-label="読了"
        >
            <Check className="w-3 h-3" />
        </span>
    );
}

export function PdfCardActionButtons({
    name,
    isSelectionMode,
    showHidden,
    isGroup,
    readState,
    onRename,
    onRegenThumb,
    onToggleHidden,
    onEditSeries,
}: PdfCardActionButtonsProps) {
    return (
        <div className="flex items-center gap-1">
            {!isSelectionMode && onRename && (
                <button
                    onClick={(e) => {
                        e.stopPropagation();
                        onRename(name);
                    }}
                    className={BTN_ICON}
                    title="名前を変更"
                >
                    <Pencil className="w-3 h-3" />
                </button>
            )}
            {!isSelectionMode && onRegenThumb && (
                <button
                    onClick={(e) => {
                        e.stopPropagation();
                        onRegenThumb(name);
                    }}
                    className={BTN_ICON}
                    title="サムネイルを再生成"
                >
                    <RefreshCw className="w-3 h-3" />
                </button>
            )}
            {!isSelectionMode && onToggleHidden && (
                <button
                    onClick={(e) => {
                        e.stopPropagation();
                        onToggleHidden(name);
                    }}
                    className={BTN_ICON}
                    title={showHidden ? '再表示する' : '非表示にする'}
                >
                    {showHidden ? <Eye className="w-3 h-3" /> : <EyeOff className="w-3 h-3" />}
                </button>
            )}
            {!isSelectionMode && onEditSeries && (
                <button
                    onClick={(e) => {
                        e.stopPropagation();
                        onEditSeries(name);
                    }}
                    className={BTN_ICON_SERIES}
                    title="シリーズを編集"
                >
                    <BookCopy className="w-3 h-3" />
                </button>
            )}
            {!isGroup && readState && <ReadStateBadge state={readState} />}
        </div>
    );
}
