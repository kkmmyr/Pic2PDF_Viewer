import { Plus, Trash2 } from 'lucide-react';

import type { useChatSessions } from '../../hooks/novel_db';

interface SessionSidebarProps {
    sessions: ReturnType<typeof useChatSessions>['sessions'];
    isLoading: boolean;
    activeId: number | null;
    onSelect: (id: number | null) => void;
    onNew: () => void;
    onDelete: (id: number) => void;
}

export function SessionSidebar({
    sessions,
    isLoading,
    activeId,
    onSelect,
    onNew,
    onDelete,
}: SessionSidebarProps) {
    return (
        <div className="border-r border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/30 max-h-[600px] overflow-y-auto">
            <button
                type="button"
                onClick={onNew}
                className="w-full flex items-center gap-1.5 px-3 py-2 text-sm font-medium border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 hover:bg-primary-50 dark:hover:bg-primary-900/30 text-gray-800 dark:text-gray-100"
            >
                <Plus className="w-4 h-4" />
                新しい会話
            </button>
            {isLoading ? (
                <p className="p-3 text-xs text-gray-500">読み込み中...</p>
            ) : sessions.length === 0 ? (
                <p className="p-3 text-xs text-gray-500">セッションなし</p>
            ) : (
                <ul>
                    {sessions.map((s) => {
                        const isActive = s.id === activeId;
                        const scopeLabel =
                            s.scope_type === 'book'
                                ? `本: ${s.scope_id ?? ''}`
                                : s.scope_type === 'series'
                                  ? `シリーズ: ${s.scope_id ?? ''}`
                                  : '全件';
                        return (
                            <li
                                key={s.id}
                                className={`group border-b border-gray-200 dark:border-gray-700 ${isActive ? 'bg-primary-50 dark:bg-primary-900/30' : ''}`}
                            >
                                <button
                                    type="button"
                                    onClick={() => onSelect(s.id)}
                                    className="w-full text-left px-3 py-2 hover:bg-gray-100 dark:hover:bg-gray-800"
                                >
                                    <div
                                        className="text-xs font-medium text-gray-900 dark:text-gray-100 truncate"
                                        title={s.title ?? `セッション ${s.id}`}
                                    >
                                        {s.title ?? `セッション ${s.id}`}
                                    </div>
                                    <div
                                        className="text-[10px] text-gray-500 dark:text-gray-400 truncate"
                                        title={scopeLabel}
                                    >
                                        {scopeLabel} · {s.message_count} 件
                                    </div>
                                </button>
                                <button
                                    type="button"
                                    onClick={() => onDelete(s.id)}
                                    title="削除"
                                    className="opacity-0 group-hover:opacity-100 absolute right-1 top-1 p-1 text-gray-500 hover:text-red-600"
                                >
                                    <Trash2 className="w-3.5 h-3.5" />
                                </button>
                            </li>
                        );
                    })}
                </ul>
            )}
        </div>
    );
}
