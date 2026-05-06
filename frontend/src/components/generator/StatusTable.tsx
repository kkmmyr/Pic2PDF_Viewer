import type { StatusItem } from '../../types';

interface StatusTableProps {
    items: StatusItem[];
}

const BADGE_CLASS: Record<StatusItem['status'], string> = {
    completed:
        'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300 border-green-200 dark:border-green-700',
    in_progress:
        'bg-primary-100 text-primary-800 dark:bg-primary-900/40 dark:text-primary-300 border-primary-200 dark:border-primary-700',
    not_started:
        'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300 border-gray-200 dark:border-gray-600',
};

const STATUS_LABEL: Record<StatusItem['status'], string> = {
    completed: '完了',
    in_progress: '処理中',
    not_started: '未着手',
};

/**
 * 生成対象アイテムのステータス一覧表。
 */
export function StatusTable({ items }: StatusTableProps) {
    if (items.length === 0) return null;

    return (
        <div className="mt-8">
            <h3 className="text-lg font-semibold text-gray-800 dark:text-gray-200 mb-4">
                アイテム状況
            </h3>
            <div className="overflow-x-auto border border-gray-200 dark:border-gray-700 rounded-lg shadow-sm">
                <table className="w-full text-left text-sm">
                    <thead className="bg-gray-50 dark:bg-gray-800 text-gray-600 dark:text-gray-400 font-medium border-b border-gray-200 dark:border-gray-700">
                        <tr>
                            <th className="px-4 py-3">名前</th>
                            <th className="px-4 py-3">種別</th>
                            <th className="px-4 py-3">状態</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                        {items.map((item) => (
                            <tr
                                key={item.name}
                                className="hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors"
                            >
                                <td className="px-4 py-3 font-medium text-gray-900 dark:text-gray-100">
                                    {item.name}
                                </td>
                                <td className="px-4 py-3 text-gray-500 dark:text-gray-400 uppercase text-[10px] tracking-wider font-semibold">
                                    {item.type}
                                </td>
                                <td className="px-4 py-3">
                                    <span
                                        className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${BADGE_CLASS[item.status]}`}
                                    >
                                        {STATUS_LABEL[item.status]}
                                    </span>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
