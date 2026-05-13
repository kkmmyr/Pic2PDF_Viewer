/**
 * 書籍メタ情報の表示コンポーネント（4.3）。
 *
 * - `card` variant: ライブラリカード用（コンパクト・ラベルなし・line-clamp）
 * - `detail` variant: 詳細ページ用（<dl> 形式・ラベルあり・フル表示）
 */
import type { BookDetail, BookSummary } from '../../features/novel_db/types';
import { formatSqliteUtcAsJst } from '../../utils/date';

interface BookMetaListProps {
    book: BookSummary | BookDetail;
    variant?: 'card' | 'detail';
}

export default function BookMetaList({ book, variant = 'detail' }: BookMetaListProps) {
    const detail = book as BookDetail;
    const seriesName = variant === 'detail'
        ? (detail.series_title ?? book.series_id)
        : book.series_id;

    if (variant === 'card') {
        return (
            <>
                {book.authors.length > 0 && (
                    <p className="text-xs text-gray-500 dark:text-gray-400 line-clamp-1">
                        {book.authors.join(' / ')}
                    </p>
                )}
                {(book.series_id || book.volume != null) && (
                    <p className="text-xs text-gray-500 dark:text-gray-400 line-clamp-1">
                        {book.series_id}
                        {book.volume != null ? ` ${book.volume}巻` : ''}
                    </p>
                )}
                {book.publisher && (
                    <p className="text-xs text-gray-400 dark:text-gray-500 line-clamp-1">
                        {book.publisher}
                    </p>
                )}
            </>
        );
    }

    return (
        <dl className="text-xs text-gray-500 dark:text-gray-400 space-y-0.5">
            {book.authors.length > 0 && (
                <div>
                    <dt className="inline font-medium">著者: </dt>
                    <dd className="inline">{book.authors.join(' / ')}</dd>
                </div>
            )}
            {seriesName && (
                <div>
                    <dt className="inline font-medium">シリーズ: </dt>
                    <dd className="inline">
                        {seriesName}
                        {book.volume != null ? ` ${book.volume}巻` : ''}
                    </dd>
                </div>
            )}
            {book.publisher && (
                <div>
                    <dt className="inline font-medium">出版社: </dt>
                    <dd className="inline">{book.publisher}</dd>
                </div>
            )}
            {book.page_count != null && (
                <div>
                    <dt className="inline font-medium">ページ数: </dt>
                    <dd className="inline">{book.page_count} ページ</dd>
                </div>
            )}
            {book.asin && (
                <div>
                    <dt className="inline font-medium">ASIN: </dt>
                    <dd className="inline font-mono">{book.asin}</dd>
                </div>
            )}
            {'isbn' in detail && detail.isbn && (
                <div>
                    <dt className="inline font-medium">ISBN: </dt>
                    <dd className="inline font-mono">{detail.isbn}</dd>
                </div>
            )}
            {book.ocr_done_at && (
                <div>
                    <dt className="inline font-medium">OCR 完了: </dt>
                    <dd className="inline">{formatSqliteUtcAsJst(book.ocr_done_at)}</dd>
                </div>
            )}
            {book.indexed_at && (
                <div>
                    <dt className="inline font-medium">構築完了: </dt>
                    <dd className="inline">{formatSqliteUtcAsJst(book.indexed_at)}</dd>
                </div>
            )}
        </dl>
    );
}
