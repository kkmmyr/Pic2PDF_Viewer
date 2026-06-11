/**
 * キャラクター詳細ダイアログ（B-15）。
 * 書籍名 × キャラ名で fetch し、サマリ + 主要シーン top 5 を表示する。
 * シーンの page_no クリックで親が `PageImageModal` を開くよう onOpenScene を呼ぶ。
 */
import { useCharacterDetail } from '@/hooks/novel_db';
import { formatSqliteUtcAsJst } from '@/utils/date';

import { Dialog, DialogBody } from '@/components/ui/dialog';

interface Props {
    /** 開く対象。null のとき非表示。 */
    bookName: string | null;
    charName: string | null;
    onClose: () => void;
    /** シーンクリック時のフック（PageImageModal を親が開く想定）。 */
    onOpenScene?: (book: string, pageNo: number) => void;
}

export default function CharacterDetailDialog({ bookName, charName, onClose, onOpenScene }: Props) {
    const open = Boolean(bookName && charName);
    const { detail, isLoading, error } = useCharacterDetail(bookName, charName);

    return (
        <Dialog
            open={open}
            title={charName ?? ''}
            subtitle={bookName ?? undefined}
            maxWidth="md"
            onClose={onClose}
        >
            <DialogBody>
                {isLoading && (
                    <p className="text-sm text-gray-500 dark:text-gray-400">読み込み中...</p>
                )}
                {error && (
                    <p className="text-sm text-red-600 dark:text-red-400">取得失敗: {error}</p>
                )}
                {!isLoading && !error && detail && (
                    <div className="space-y-3">
                        <div className="text-xs text-gray-500 dark:text-gray-400">
                            初登場 p{detail.first_page} / 登場 {detail.page_count} ページ
                            {detail.generated_at && (
                                <span className="ml-2 opacity-70">
                                    生成 {formatSqliteUtcAsJst(detail.generated_at)}
                                </span>
                            )}
                        </div>
                        {detail.summary ? (
                            <p className="text-sm text-gray-800 dark:text-gray-200 whitespace-pre-wrap leading-relaxed">
                                {detail.summary}
                            </p>
                        ) : (
                            <p className="text-sm text-gray-500 dark:text-gray-400 italic">
                                サマリ未生成
                            </p>
                        )}
                        {detail.top_scenes.length > 0 && (
                            <div>
                                <h3 className="text-xs font-semibold text-gray-700 dark:text-gray-300 mb-1.5">
                                    主要シーン
                                </h3>
                                <ul className="flex flex-wrap gap-1.5">
                                    {detail.top_scenes.map((s) => (
                                        <li key={s.page_no}>
                                            <button
                                                type="button"
                                                onClick={() => {
                                                    if (bookName && onOpenScene) {
                                                        onOpenScene(bookName, s.page_no);
                                                    }
                                                }}
                                                className="text-xs px-2 py-1 rounded bg-gray-100 dark:bg-gray-800 hover:bg-primary-50 dark:hover:bg-primary-900/30 text-gray-800 dark:text-gray-200"
                                                title={`page ${s.page_no}（${s.char_count} 字）`}
                                            >
                                                p{s.page_no}
                                                <span className="ml-1 opacity-60">
                                                    {s.char_count}字
                                                </span>
                                            </button>
                                        </li>
                                    ))}
                                </ul>
                            </div>
                        )}
                    </div>
                )}
            </DialogBody>
        </Dialog>
    );
}
