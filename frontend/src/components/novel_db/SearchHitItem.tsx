/**
 * 検索結果 1 件分のカード。サムネイル + 書名 + page 番号 + ハイライト snippet。
 * snippet はバックエンドで `<mark>` のみ許可済みなので dangerouslySetInnerHTML で安全。
 */
import type { SearchHit } from '../../features/novel_db/types';

interface Props {
    hit: SearchHit;
    onOpenImage: (book: string, pageNo: number) => void;
}

export default function SearchHitItem({ hit, onOpenImage }: Props) {
    return (
        <article className="flex gap-3 p-3 border border-gray-200 dark:border-gray-700 rounded-md bg-white dark:bg-gray-800">
            {hit.image_url ? (
                <button
                    onClick={() => onOpenImage(hit.book_name, hit.page_no)}
                    className="flex-shrink-0 w-16 sm:w-20 aspect-[3/4] overflow-hidden rounded border border-gray-200 dark:border-gray-700 hover:ring-2 hover:ring-primary-500 transition"
                    title="クリックで画像を拡大"
                >
                    <img
                        src={hit.image_url}
                        alt={`${hit.book_name} page ${hit.page_no}`}
                        className="w-full h-full object-cover"
                        loading="lazy"
                    />
                </button>
            ) : (
                <div className="flex-shrink-0 w-16 sm:w-20 aspect-[3/4] rounded bg-gray-100 dark:bg-gray-900 flex items-center justify-center text-xs text-gray-400">
                    画像なし
                </div>
            )}
            <div className="min-w-0 flex-1">
                <div className="flex items-baseline gap-2 flex-wrap">
                    <button
                        onClick={() => onOpenImage(hit.book_name, hit.page_no)}
                        className="text-sm font-medium text-primary-700 dark:text-primary-300 hover:underline"
                    >
                        {hit.book_name} <span className="text-gray-500">page {hit.page_no}</span>
                    </button>
                    <span className="text-xs text-gray-400">score {hit.rrf_score.toFixed(3)}</span>
                </div>
                <p
                    className="text-sm text-gray-700 dark:text-gray-300 mt-1 line-clamp-3 leading-relaxed [&_mark]:bg-yellow-200 [&_mark]:dark:bg-yellow-800 [&_mark]:rounded [&_mark]:px-0.5"
                    dangerouslySetInnerHTML={{ __html: hit.snippet }}
                />
            </div>
        </article>
    );
}
