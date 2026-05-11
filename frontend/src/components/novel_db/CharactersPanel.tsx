/**
 * 書籍カード内に折りたたみ表示する登場人物一覧（B-15）。
 *
 * 親（BookCard）の expanded 状態で表示制御する。展開された時のみ
 * `useBookCharacters` が API を叩く（enabled パラメータ経由）。
 */
import { Users } from 'lucide-react';

import { useBookCharacters } from '../../hooks/novel_db';

interface Props {
    bookName: string;
    expanded: boolean;
    onSelect: (charName: string) => void;
}

export default function CharactersPanel({ bookName, expanded, onSelect }: Props) {
    const { characters, isLoading, error } = useBookCharacters(bookName, expanded);

    if (!expanded) return null;

    return (
        <div className="border-t border-gray-200 dark:border-gray-700 px-3 py-2 bg-gray-50 dark:bg-gray-900/40">
            <div className="flex items-center gap-1.5 text-xs text-gray-600 dark:text-gray-400 mb-1.5">
                <Users className="w-3 h-3" />
                <span>登場人物</span>
            </div>
            {isLoading ? (
                <p className="text-xs text-gray-500 dark:text-gray-400">読み込み中...</p>
            ) : error ? (
                <p className="text-xs text-red-600 dark:text-red-400">取得失敗: {error}</p>
            ) : characters.length === 0 ? (
                <p className="text-xs text-gray-500 dark:text-gray-400">キャラ辞典 未生成</p>
            ) : (
                <ul className="flex flex-wrap gap-1.5">
                    {characters.map((c) => (
                        <li key={c.name}>
                            <button
                                type="button"
                                onClick={() => onSelect(c.name)}
                                disabled={!c.has_summary}
                                title={
                                    c.has_summary
                                        ? `${c.page_count} ページ登場 / 初登場 p${c.first_page}`
                                        : 'サマリ未生成'
                                }
                                className="text-xs px-2 py-0.5 rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 hover:bg-primary-50 dark:hover:bg-primary-900/30 text-gray-800 dark:text-gray-200 disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                {c.name}
                                <span className="ml-1 opacity-60">×{c.page_count}</span>
                            </button>
                        </li>
                    ))}
                </ul>
            )}
        </div>
    );
}
