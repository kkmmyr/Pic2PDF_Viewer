import { useState, useRef, useEffect, useMemo, useLayoutEffect } from 'react';
import { ChevronDown, X } from 'lucide-react';

interface SearchableSelectProps {
    /** 選択中の値（空文字なら未選択 = "すべて"） */
    value: string;
    /** 選択肢一覧 */
    options: string[];
    /** value === '' に対応するラベル（例: "作者: すべて"） */
    emptyLabel: string;
    /** 入力欄の placeholder（フォーカス時かつ value 空時の表示） */
    placeholder?: string;
    onChange: (value: string) => void;
    /** ルート要素に追加するクラス（幅調整など） */
    className?: string;
}

/**
 * テキスト入力で絞り込めるドロップダウン。`<select>` の代替。
 *
 * - 入力テキストで部分一致フィルタ（大文字小文字無視）
 * - キーボード: ↑↓ で移動、Enter で確定、Esc で閉じる
 * - X ボタンで選択クリア、外クリックで閉じる
 */
export function SearchableSelect({
    value,
    options,
    emptyLabel,
    placeholder,
    onChange,
    className = '',
}: SearchableSelectProps) {
    const [isOpen, setIsOpen] = useState(false);
    const [query, setQuery] = useState('');
    const [highlight, setHighlight] = useState(0);
    const containerRef = useRef<HTMLDivElement>(null);
    const inputRef = useRef<HTMLInputElement>(null);
    const listRef = useRef<HTMLUListElement>(null);

    // 表示用アイテム: 先頭に「すべて (空文字 value)」+ フィルタ済み options
    const items = useMemo(() => {
        const q = query.trim().toLowerCase();
        const filtered = q
            ? options.filter(o => o.toLowerCase().includes(q))
            : options;
        return [{ value: '', label: emptyLabel }, ...filtered.map(o => ({ value: o, label: o }))];
    }, [options, query, emptyLabel]);

    // 外クリックで閉じる
    useEffect(() => {
        if (!isOpen) return;
        const onMouseDown = (e: MouseEvent) => {
            if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
                setIsOpen(false);
                setQuery('');
            }
        };
        document.addEventListener('mousedown', onMouseDown);
        return () => document.removeEventListener('mousedown', onMouseDown);
    }, [isOpen]);

    // ハイライト位置がリスト範囲外になったら 0 に丸める
    useEffect(() => {
        if (highlight >= items.length) setHighlight(0);
    }, [highlight, items.length]);

    // ハイライト変更時にスクロール追従
    useLayoutEffect(() => {
        if (!isOpen || !listRef.current) return;
        const el = listRef.current.children[highlight] as HTMLElement | undefined;
        el?.scrollIntoView({ block: 'nearest' });
    }, [highlight, isOpen]);

    const open = () => {
        setIsOpen(true);
        setQuery('');
        setHighlight(0);
    };

    const select = (val: string) => {
        onChange(val);
        setIsOpen(false);
        setQuery('');
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            if (!isOpen) { open(); return; }
            setHighlight(h => Math.min(h + 1, items.length - 1));
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            if (!isOpen) { open(); return; }
            setHighlight(h => Math.max(h - 1, 0));
        } else if (e.key === 'Enter') {
            if (!isOpen) return;
            e.preventDefault();
            const item = items[highlight];
            if (item) select(item.value);
        } else if (e.key === 'Escape') {
            if (!isOpen) return;
            e.preventDefault();
            setIsOpen(false);
            setQuery('');
        }
    };

    // 入力欄の表示: 開いてる間は query、閉じている間は選択中の value
    const displayValue = isOpen ? query : value;

    return (
        <div ref={containerRef} className={`relative ${className}`}>
            <div className="flex items-center border border-gray-200 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 focus-within:ring-2 focus-within:ring-blue-400">
                <input
                    ref={inputRef}
                    type="text"
                    value={displayValue}
                    onChange={(e) => {
                        setQuery(e.target.value);
                        setIsOpen(true);
                        setHighlight(0);
                    }}
                    onFocus={() => { if (!isOpen) open(); }}
                    onKeyDown={handleKeyDown}
                    placeholder={isOpen ? (placeholder ?? '入力で絞り込み') : emptyLabel}
                    className="px-2 py-1 text-sm text-gray-700 dark:text-gray-300 bg-transparent focus:outline-none flex-1 min-w-0"
                />
                {value && !isOpen && (
                    <button
                        type="button"
                        onClick={() => select('')}
                        className="px-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
                        title="クリア"
                    >
                        <X className="w-3.5 h-3.5" />
                    </button>
                )}
                <button
                    type="button"
                    onClick={() => {
                        if (isOpen) {
                            setIsOpen(false);
                            setQuery('');
                        } else {
                            open();
                            inputRef.current?.focus();
                        }
                    }}
                    className="px-1.5 py-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
                    aria-label={isOpen ? '閉じる' : '開く'}
                >
                    <ChevronDown className={`w-3.5 h-3.5 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
                </button>
            </div>
            {isOpen && (
                <ul
                    ref={listRef}
                    className="absolute top-full left-0 right-0 mt-1 max-h-60 overflow-auto border border-gray-200 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 shadow-lg z-header"
                >
                    {items.length === 1 && query.trim() ? (
                        <li className="px-2 py-1 text-sm text-gray-400 dark:text-gray-500">該当なし</li>
                    ) : (
                        items.map((item, i) => (
                            <li
                                key={item.value || '__empty__'}
                                onMouseDown={(e) => { e.preventDefault(); select(item.value); }}
                                onMouseEnter={() => setHighlight(i)}
                                className={`px-2 py-1 text-sm cursor-pointer truncate ${
                                    i === highlight
                                        ? 'bg-blue-100 dark:bg-blue-900/40 text-blue-800 dark:text-blue-200'
                                        : 'text-gray-700 dark:text-gray-300'
                                } ${item.value === value ? 'font-semibold' : ''}`}
                            >
                                {item.label}
                            </li>
                        ))
                    )}
                </ul>
            )}
        </div>
    );
}
