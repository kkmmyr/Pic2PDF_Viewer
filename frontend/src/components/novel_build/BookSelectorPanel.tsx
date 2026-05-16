import { Loader2 } from 'lucide-react';

type ButtonVariant = 'primary' | 'secondary' | 'indigo';

const BUTTON_COLOR: Record<ButtonVariant, string> = {
    primary: 'bg-primary-600 hover:bg-primary-700',
    secondary: 'bg-gray-600 hover:bg-gray-700',
    indigo: 'bg-indigo-600 hover:bg-indigo-700',
};

const SELECT_CLASS =
    'w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-primary-500';

interface BookSelectorPanelProps {
    title: string;
    icon: React.ReactNode;
    allBooks: boolean;
    setAllBooks: (v: boolean) => void;
    /** 未完了/完了済みフィルタ。指定しない場合はフィルタ行を非表示 */
    showBuilt?: boolean;
    onShowBuiltChange?: (v: boolean) => void;
    books: { name: string }[];
    selectedBook: string;
    setSelectedBook: (v: string) => void;
    onEnqueue: () => void;
    isEnqueuing: boolean;
    buttonLabel: string;
    buttonIcon: React.ReactNode;
    buttonVariant?: ButtonVariant;
    className?: string;
}

export default function BookSelectorPanel({
    title,
    icon,
    allBooks,
    setAllBooks,
    showBuilt,
    onShowBuiltChange,
    books,
    selectedBook,
    setSelectedBook,
    onEnqueue,
    isEnqueuing,
    buttonLabel,
    buttonIcon,
    buttonVariant = 'primary',
    className = '',
}: BookSelectorPanelProps) {
    const hasFilter = showBuilt !== undefined && onShowBuiltChange !== undefined;

    return (
        <div
            className={`bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl p-5 ${className}`}
        >
            <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-4 flex items-center gap-2">
                {icon}
                {title}
            </h2>
            <div className="flex flex-col gap-3">
                {/* 個別/全冊 */}
                <div className="flex gap-4 text-sm">
                    <label className="flex items-center gap-2 cursor-pointer">
                        <input
                            type="radio"
                            checked={!allBooks}
                            onChange={() => setAllBooks(false)}
                            className="text-primary-500"
                        />
                        <span className="text-gray-700 dark:text-gray-300">個別指定</span>
                    </label>
                    <label className="flex items-center gap-2 cursor-pointer">
                        <input
                            type="radio"
                            checked={allBooks}
                            onChange={() => setAllBooks(true)}
                            className="text-primary-500"
                        />
                        <span className="text-gray-700 dark:text-gray-300">全冊</span>
                    </label>
                </div>

                {!allBooks && (
                    <>
                        {/* 未完了/完了済みフィルタ */}
                        {hasFilter && (
                            <div className="flex gap-4 text-sm ml-1">
                                <label className="flex items-center gap-1.5 cursor-pointer">
                                    <input
                                        type="radio"
                                        checked={!showBuilt}
                                        onChange={() => onShowBuiltChange!(false)}
                                        className="text-primary-500"
                                    />
                                    <span className="text-gray-600 dark:text-gray-400">未完了</span>
                                </label>
                                <label className="flex items-center gap-1.5 cursor-pointer">
                                    <input
                                        type="radio"
                                        checked={showBuilt}
                                        onChange={() => onShowBuiltChange!(true)}
                                        className="text-primary-500"
                                    />
                                    <span className="text-gray-600 dark:text-gray-400">
                                        完了済み
                                    </span>
                                </label>
                            </div>
                        )}

                        {/* 書籍選択 */}
                        <select
                            value={selectedBook}
                            onChange={(e) => setSelectedBook(e.target.value)}
                            className={SELECT_CLASS}
                        >
                            {books.map((b) => (
                                <option key={b.name} value={b.name}>
                                    {b.name}
                                </option>
                            ))}
                            {books.length === 0 && (
                                <option value="">（書籍が見つかりません）</option>
                            )}
                        </select>
                    </>
                )}

                {/* 実行ボタン */}
                <button
                    onClick={onEnqueue}
                    disabled={isEnqueuing || (!allBooks && !selectedBook)}
                    className={`flex items-center justify-center gap-2 px-4 py-2 ${BUTTON_COLOR[buttonVariant]} disabled:bg-gray-300 dark:disabled:bg-gray-700 text-white text-sm font-medium rounded-lg transition-colors`}
                >
                    {isEnqueuing ? <Loader2 className="w-4 h-4 animate-spin" /> : buttonIcon}
                    {buttonLabel}
                </button>
            </div>
        </div>
    );
}
