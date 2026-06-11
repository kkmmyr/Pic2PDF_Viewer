import { ExternalLink, EyeOff, FileText } from 'lucide-react';
import type { ArrivalItem } from '@/types/hitomi';
import { formatDateJa } from '@/utils/date';

interface HitomiArrivalCardProps {
    item: ArrivalItem;
    onDismiss: (id: number) => void;
}

export function HitomiArrivalCard({ item, onDismiss }: HitomiArrivalCardProps) {
    return (
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 flex flex-col gap-2 hover:shadow-md transition-shadow">
            <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 line-clamp-2 break-all">
                {item.title || '(タイトル不明)'}
            </h3>
            <div className="text-xs text-gray-500 dark:text-gray-400 flex flex-wrap gap-x-3 gap-y-1">
                <span>作者: {item.display_artist || item.artist}</span>
                {item.type && <span>種別: {item.type}</span>}
                <span className="flex items-center gap-1">
                    <FileText className="w-3 h-3" />
                    {item.page_count} ページ
                </span>
            </div>
            <div className="text-xs text-gray-400 dark:text-gray-500">
                {item.published_at && <span>公開: {formatDateJa(item.published_at)}</span>}
                {item.published_at && item.discovered_at && <span> / </span>}
                {item.discovered_at && <span>検出: {formatDateJa(item.discovered_at)}</span>}
            </div>
            <div className="flex gap-2 mt-1">
                <a
                    href={item.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium bg-primary-600 hover:bg-primary-700 text-white transition-colors"
                >
                    <ExternalLink className="w-3.5 h-3.5" />
                    hitomi.la で開く
                </a>
                <button
                    onClick={() => onDismiss(item.id)}
                    className="inline-flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
                    title="既読化"
                >
                    <EyeOff className="w-3.5 h-3.5" />
                    既読
                </button>
            </div>
        </div>
    );
}
