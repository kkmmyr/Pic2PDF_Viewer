import { BookCopy, User, Tag } from 'lucide-react';
import type { RelatedBooks } from '../../hooks/useRelatedBooks';

interface RelatedBooksPanelProps {
    related: RelatedBooks;
    onSelect: (name: string) => void;
}

function stripPdfExt(name: string): string {
    return name.replace(/\.pdf$/i, '');
}

/**
 * 関連書籍パネル（最終ページ到達時の右下フローティングカード）。
 *
 * 同シリーズ / 同作者 / 共通タグ の 3 セクションを表示。
 * 全セクションが空なら何も描画しない（呼び出し側の条件分岐は不要）。
 */
export function RelatedBooksPanel({ related, onSelect }: RelatedBooksPanelProps) {
    const { series, authors, tags } = related;
    if (series.length === 0 && authors.length === 0 && tags.length === 0) return null;

    return (
        <aside
            className="fixed right-6 bottom-20 z-overlay-bar w-72 max-h-[60vh] overflow-y-auto rounded-lg shadow-2xl bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 p-3 text-sm"
            aria-label="関連書籍"
        >
            <h2 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-2">
                関連書籍
            </h2>

            {series.length > 0 && (
                <section className="mb-3">
                    <h3 className="flex items-center gap-1.5 text-xs font-semibold text-accent-700 dark:text-accent-300 mb-1.5">
                        <BookCopy className="w-3.5 h-3.5" />
                        同シリーズ
                    </h3>
                    <ul className="space-y-1">
                        {series.map((b) => (
                            <li key={`series-${b.name}`}>
                                <button
                                    onClick={() => onSelect(b.name)}
                                    className="w-full text-left px-2 py-1 rounded hover:bg-accent-50 dark:hover:bg-accent-900/30 text-gray-800 dark:text-gray-200 truncate"
                                    title={`#${b.seriesIndex} ${stripPdfExt(b.name)}`}
                                >
                                    <span className="text-accent-600 dark:text-accent-400 font-medium">
                                        #{b.seriesIndex}
                                    </span>{' '}
                                    {stripPdfExt(b.name)}
                                </button>
                            </li>
                        ))}
                    </ul>
                </section>
            )}

            {authors.length > 0 && (
                <section className="mb-3">
                    <h3 className="flex items-center gap-1.5 text-xs font-semibold text-primary-700 dark:text-primary-300 mb-1.5">
                        <User className="w-3.5 h-3.5" />
                        同じ作者
                    </h3>
                    <ul className="space-y-1">
                        {authors.map((b) => (
                            <li key={`author-${b.name}`}>
                                <button
                                    onClick={() => onSelect(b.name)}
                                    className="w-full text-left px-2 py-1 rounded hover:bg-primary-50 dark:hover:bg-primary-900/30 text-gray-800 dark:text-gray-200 truncate"
                                    title={stripPdfExt(b.name)}
                                >
                                    {stripPdfExt(b.name)}
                                </button>
                            </li>
                        ))}
                    </ul>
                </section>
            )}

            {tags.length > 0 && (
                <section>
                    <h3 className="flex items-center gap-1.5 text-xs font-semibold text-emerald-700 dark:text-emerald-300 mb-1.5">
                        <Tag className="w-3.5 h-3.5" />
                        共通タグ
                    </h3>
                    <ul className="space-y-1">
                        {tags.map((b) => (
                            <li key={`tag-${b.name}`}>
                                <button
                                    onClick={() => onSelect(b.name)}
                                    className="w-full text-left px-2 py-1 rounded hover:bg-emerald-50 dark:hover:bg-emerald-900/30 text-gray-800 dark:text-gray-200 truncate"
                                    title={stripPdfExt(b.name)}
                                >
                                    {stripPdfExt(b.name)}
                                </button>
                            </li>
                        ))}
                    </ul>
                </section>
            )}
        </aside>
    );
}
