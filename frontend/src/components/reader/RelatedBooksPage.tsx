import { BookCopy, User } from 'lucide-react';
import type { RelatedBooks } from '../../hooks/useRelatedBooks';
import type { LibrarySource } from '../../types';
import { API_ENDPOINTS } from '../../config/api';
import { LazyThumbnail } from '../library/LazyThumbnail';

interface RelatedBooksPageProps {
    related: RelatedBooks;
    currentPath: string;
    currentSource: LibrarySource;
    onSelect: (name: string) => void;
}

function stripPdfExt(name: string): string {
    return name.replace(/\.pdf$/i, '');
}

/**
 * 関連書籍ページ（最終ページの次の仮想ページとして表示）。
 *
 * 「同シリーズ → 同作者」のカードグリッドで、表紙サムネイル + タイトルを提示する。
 * 見開きモードに関係なく単独中央表示。
 */
export function RelatedBooksPage({
    related,
    currentPath,
    currentSource,
    onSelect,
}: RelatedBooksPageProps) {
    const { series, authors } = related;

    return (
        <div className="min-h-full p-6 max-w-6xl mx-auto" aria-label="関連書籍">
            <h2 className="text-lg font-semibold text-gray-700 dark:text-gray-300 mb-6">
                関連書籍
            </h2>

            {series.length > 0 && (
                <section className="mb-8">
                    <h3 className="flex items-center gap-2 text-sm font-semibold text-accent-700 dark:text-accent-300 mb-3">
                        <BookCopy className="w-4 h-4" />
                        同シリーズ
                    </h3>
                    <ul className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-4">
                        {series.map((b) => (
                            <li key={`series-${b.name}`}>
                                <button
                                    onClick={() => onSelect(b.name)}
                                    className="w-full text-left rounded-lg overflow-hidden bg-white dark:bg-gray-800 shadow hover:shadow-lg transition-shadow"
                                    title={`#${b.seriesIndex} ${stripPdfExt(b.name)}`}
                                >
                                    <div className="aspect-[3/4] relative">
                                        <LazyThumbnail
                                            src={API_ENDPOINTS.PAGE_THUMBNAIL(
                                                b.name,
                                                1,
                                                currentPath,
                                                currentSource,
                                            )}
                                            alt={stripPdfExt(b.name)}
                                            className="absolute inset-0"
                                        />
                                        <div className="absolute top-2 left-2 z-card-badge px-2 py-0.5 rounded-full bg-accent-700 text-white text-xs font-semibold shadow">
                                            #{b.seriesIndex}
                                        </div>
                                    </div>
                                    <div className="p-2 text-sm text-gray-800 dark:text-gray-200 line-clamp-2">
                                        {stripPdfExt(b.name)}
                                    </div>
                                </button>
                            </li>
                        ))}
                    </ul>
                </section>
            )}

            {authors.length > 0 && (
                <section>
                    <h3 className="flex items-center gap-2 text-sm font-semibold text-primary-700 dark:text-primary-300 mb-3">
                        <User className="w-4 h-4" />
                        同じ作者
                    </h3>
                    <ul className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-4">
                        {authors.map((b) => (
                            <li key={`author-${b.name}`}>
                                <button
                                    onClick={() => onSelect(b.name)}
                                    className="w-full text-left rounded-lg overflow-hidden bg-white dark:bg-gray-800 shadow hover:shadow-lg transition-shadow"
                                    title={stripPdfExt(b.name)}
                                >
                                    <div className="aspect-[3/4] relative">
                                        <LazyThumbnail
                                            src={API_ENDPOINTS.PAGE_THUMBNAIL(
                                                b.name,
                                                1,
                                                currentPath,
                                                currentSource,
                                            )}
                                            alt={stripPdfExt(b.name)}
                                            className="absolute inset-0"
                                        />
                                    </div>
                                    <div className="p-2 text-sm text-gray-800 dark:text-gray-200 line-clamp-2">
                                        {stripPdfExt(b.name)}
                                    </div>
                                </button>
                            </li>
                        ))}
                    </ul>
                </section>
            )}
        </div>
    );
}
