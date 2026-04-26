import { useEffect, useRef, useState } from 'react';
import { Search, X, ChevronUp, ChevronDown } from 'lucide-react';
import { UI_CONFIG } from '../../constants';

interface PdfSearchBarProps {
    /** 検索テキスト */
    searchText: string;
    matchCount: number;
    currentMatch: number;
    onSearchChange: (text: string) => void;
    onPrevMatch: () => void;
    onNextMatch: () => void;
    onClose: () => void;
}

/**
 * PDF内テキスト検索バー。
 * ReaderHeader の下に固定表示し、入力に応じて親へ検索テキストを通知する。
 */
export function PdfSearchBar({
    searchText,
    matchCount,
    currentMatch,
    onSearchChange,
    onPrevMatch,
    onNextMatch,
    onClose,
}: PdfSearchBarProps) {
    const inputRef = useRef<HTMLInputElement>(null);
    const [localText, setLocalText] = useState(searchText);

    // 開いた瞬間にフォーカス
    useEffect(() => {
        inputRef.current?.focus();
    }, []);

    // localText が変わったら 300ms デバウンスして親へ通知
    useEffect(() => {
        const timer = setTimeout(() => {
            onSearchChange(localText);
        }, UI_CONFIG.SEARCH_DEBOUNCE_MS);
        return () => clearTimeout(timer);
    }, [localText, onSearchChange]);

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter') {
            e.shiftKey ? onPrevMatch() : onNextMatch();
        }
        if (e.key === 'Escape') {
            onClose();
        }
    };

    return (
        <div className="fixed top-14 left-0 right-0 z-40 flex items-center gap-2 px-4 py-2 bg-white/95 dark:bg-gray-900/95 border-b border-gray-200 dark:border-gray-700 shadow-sm backdrop-blur-sm animate-in slide-in-from-top-1 duration-150">
            <Search className="w-4 h-4 text-gray-400 dark:text-gray-500 shrink-0" />
            <input
                ref={inputRef}
                type="text"
                value={localText}
                onChange={(e) => setLocalText(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="PDFテキストを検索..."
                className="flex-1 bg-transparent text-sm text-gray-800 dark:text-gray-200 outline-none placeholder-gray-400 dark:placeholder-gray-500"
            />
            {matchCount > 0 && (
                <span className="text-xs text-gray-500 dark:text-gray-400 shrink-0 min-w-[60px] text-right">
                    {currentMatch} / {matchCount}
                </span>
            )}
            {localText && matchCount === 0 && (
                <span className="text-xs text-red-500 dark:text-red-400 shrink-0">
                    見つかりません
                </span>
            )}
            <div className="flex items-center gap-1 shrink-0">
                <button
                    onClick={onPrevMatch}
                    disabled={matchCount === 0}
                    className="p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-40"
                    title="前の結果 (Shift+Enter)"
                >
                    <ChevronUp className="w-4 h-4 text-gray-600 dark:text-gray-400" />
                </button>
                <button
                    onClick={onNextMatch}
                    disabled={matchCount === 0}
                    className="p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-40"
                    title="次の結果 (Enter)"
                >
                    <ChevronDown className="w-4 h-4 text-gray-600 dark:text-gray-400" />
                </button>
                <button
                    onClick={onClose}
                    className="p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-800"
                    title="閉じる (Esc)"
                >
                    <X className="w-4 h-4 text-gray-600 dark:text-gray-400" />
                </button>
            </div>
        </div>
    );
}
