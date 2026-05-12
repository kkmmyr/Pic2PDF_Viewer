/**
 * 書籍 1 冊のサムネイル + メタ情報 + 再構築ボタン + 登場人物トグル（B-15）。
 */
import { useState } from 'react';
import { CheckCircle2, ChevronDown, ChevronUp, Circle, RefreshCw, ScanText, Users } from 'lucide-react';

import type { BookSummary } from '../../features/novel_db/types';

import CharactersPanel from './CharactersPanel';

interface Props {
    book: BookSummary;
    onRebuild: (bookName: string) => void;
    onOcr: (bookName: string) => void;
    onRead: (bookName: string) => void;
    /** B-15: キャラ選択時に親が CharacterDetailDialog を開く。 */
    onSelectCharacter?: (bookName: string, charName: string) => void;
    disabled?: boolean;
}

function formatIndexedAt(isoLike: string | null): string | null {
    if (!isoLike) return null;
    // "2026-05-09 21:50:43" のような SQLite datetime をそのまま表示
    return isoLike.replace('T', ' ').slice(0, 16);
}

export default function BookCard({ book, onRebuild, onOcr, onRead, onSelectCharacter, disabled }: Props) {
    const indexedAt = formatIndexedAt(book.indexed_at);
    const [charsExpanded, setCharsExpanded] = useState(false);
    return (
        <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden bg-white dark:bg-gray-800 flex flex-col">
            <button
                className="w-full text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-500"
                onClick={() => onRead(book.name)}
                aria-label={`${book.name} を読む`}
            >
                {book.thumbnail_url ? (
                    <img
                        src={book.thumbnail_url}
                        alt={book.name}
                        className="w-full aspect-[3/4] object-cover bg-gray-100 dark:bg-gray-900 hover:opacity-90 transition-opacity"
                        loading="lazy"
                    />
                ) : (
                    <div className="w-full aspect-[3/4] bg-gray-100 dark:bg-gray-900 flex items-center justify-center text-gray-400 text-sm hover:bg-gray-200 dark:hover:bg-gray-800 transition-colors">
                        画像なし
                    </div>
                )}
            </button>
            <div className="p-3 flex-1 flex flex-col gap-2">
                <h3
                    className="text-sm font-medium text-gray-900 dark:text-gray-100 line-clamp-2"
                    title={book.name}
                >
                    {book.name}
                </h3>
                {book.authors.length > 0 && (
                    <p className="text-xs text-gray-500 dark:text-gray-400 line-clamp-1">
                        {book.authors.join(' / ')}
                    </p>
                )}
                <div className="flex items-center gap-1.5 text-xs">
                    {book.is_indexed ? (
                        <>
                            <CheckCircle2 className="w-3.5 h-3.5 text-green-600 dark:text-green-400" />
                            <span className="text-gray-600 dark:text-gray-400">
                                {book.page_count} ページ
                            </span>
                            {indexedAt && (
                                <span className="text-gray-400 dark:text-gray-500 ml-auto">
                                    {indexedAt}
                                </span>
                            )}
                        </>
                    ) : (
                        <>
                            <Circle className="w-3.5 h-3.5 text-gray-400" />
                            <span className="text-gray-500 dark:text-gray-400">未構築</span>
                        </>
                    )}
                </div>
                <button
                    onClick={() => onOcr(book.name)}
                    disabled={disabled}
                    title={book.ocr_done_at ? `OCR 済み: ${book.ocr_done_at.slice(0, 16)}` : 'OCR 未実施'}
                    className={`mt-1 px-2.5 py-1 text-xs rounded flex items-center justify-center gap-1 disabled:opacity-50 disabled:cursor-not-allowed ${
                        book.ocr_done_at
                            ? 'bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-200'
                            : 'bg-amber-100 dark:bg-amber-900/40 hover:bg-amber-200 dark:hover:bg-amber-800/60 text-amber-800 dark:text-amber-300'
                    }`}
                >
                    <ScanText className="w-3 h-3" />
                    OCR
                </button>
                <button
                    onClick={() => onRebuild(book.name)}
                    disabled={disabled}
                    className="px-2.5 py-1 text-xs rounded bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-200 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-1"
                >
                    <RefreshCw className="w-3 h-3" />
                    再構築
                </button>
                {book.is_indexed && (
                    <button
                        type="button"
                        onClick={() => setCharsExpanded((v) => !v)}
                        className="px-2.5 py-1 text-xs rounded bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-200 flex items-center justify-center gap-1"
                        aria-expanded={charsExpanded}
                    >
                        <Users className="w-3 h-3" />
                        登場人物
                        {charsExpanded ? (
                            <ChevronUp className="w-3 h-3" />
                        ) : (
                            <ChevronDown className="w-3 h-3" />
                        )}
                    </button>
                )}
            </div>
            {book.is_indexed && onSelectCharacter && (
                <CharactersPanel
                    bookName={book.name}
                    expanded={charsExpanded}
                    onSelect={(charName) => onSelectCharacter(book.name, charName)}
                />
            )}
        </div>
    );
}
