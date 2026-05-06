import { useState } from 'react';
import { Plus, Trash2, Loader2 } from 'lucide-react';
import { Dialog, DialogBody, DialogFooter, DialogCancelButton } from '../ui/Dialog';
import { ConfirmDialog } from '../ui/ConfirmDialog';
import { useHitomiWatchlist } from '../../hooks/useHitomiWatchlist';
import { ApiError } from '../../config/api_client';
import { errorMessage } from '../../utils/error';
import type { WatchlistEntry } from '../../types/hitomi';

interface HitomiWatchlistDialogProps {
    open: boolean;
    onClose: () => void;
    onError: (msg: string) => void;
    onSuccess: (msg: string) => void;
}

const LANGUAGE_OPTIONS = [
    { value: 'japanese', label: '日本語' },
    { value: 'english', label: 'English' },
    { value: 'chinese', label: '中文' },
];

export function HitomiWatchlistDialog({
    open,
    onClose,
    onError,
    onSuccess,
}: HitomiWatchlistDialogProps) {
    const { artists, loading, error, addArtist, removeArtist } = useHitomiWatchlist();
    const [name, setName] = useState('');
    const [language, setLanguage] = useState('japanese');
    const [submitting, setSubmitting] = useState(false);
    const [confirmTarget, setConfirmTarget] = useState<WatchlistEntry | null>(null);

    const handleAdd = async () => {
        const trimmed = name.trim();
        if (!trimmed) return;
        setSubmitting(true);
        try {
            await addArtist(trimmed, language);
            onSuccess(`${trimmed} を監視対象に追加しました`);
            setName('');
        } catch (e) {
            if (e instanceof ApiError) {
                if (e.status === 404) {
                    onError(
                        `hitomi.la に「${trimmed}」が見つかりません。スペル・空白の有無を確認してください`,
                    );
                } else if (e.status === 400) {
                    onError(e.message);
                } else {
                    onError(`追加に失敗しました: ${e.message}`);
                }
            } else {
                onError(errorMessage(e, '追加に失敗しました'));
            }
        } finally {
            setSubmitting(false);
        }
    };

    const handleConfirmRemove = async () => {
        if (!confirmTarget) return;
        const target = confirmTarget;
        setConfirmTarget(null);
        try {
            await removeArtist(target.normalized, target.language);
            onSuccess(`${target.display_name} を削除しました`);
        } catch (e) {
            onError(errorMessage(e, '削除に失敗しました'));
        }
    };

    return (
        <Dialog open={open} title="監視対象を編集" onClose={onClose} maxWidth="md">
            <DialogBody>
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
                    監視対象を変更しても、次回の監視実行までは新着一覧に反映されません。
                </p>

                {/* 追加フォーム */}
                <div className="flex gap-2 mb-4">
                    <input
                        type="text"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        onKeyDown={(e) => {
                            if (e.key === 'Enter') {
                                e.preventDefault();
                                handleAdd();
                            }
                        }}
                        placeholder="作者名（例: aka shio）"
                        className="flex-1 px-3 py-1.5 text-sm rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 outline-none focus:ring-2 focus:ring-blue-500"
                        disabled={submitting}
                    />
                    <select
                        value={language}
                        onChange={(e) => setLanguage(e.target.value)}
                        className="px-2 py-1.5 text-sm rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 outline-none focus:ring-2 focus:ring-blue-500"
                        disabled={submitting}
                    >
                        {LANGUAGE_OPTIONS.map((opt) => (
                            <option key={opt.value} value={opt.value}>
                                {opt.label}
                            </option>
                        ))}
                    </select>
                    <button
                        onClick={handleAdd}
                        disabled={submitting || !name.trim()}
                        className="inline-flex items-center gap-1 px-3 py-1.5 rounded-md text-sm font-medium bg-primary-600 hover:bg-primary-700 text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        {submitting ? (
                            <Loader2 className="w-4 h-4 animate-spin" />
                        ) : (
                            <Plus className="w-4 h-4" />
                        )}
                        追加
                    </button>
                </div>

                {/* 一覧 */}
                <div className="border-t border-gray-200 dark:border-gray-700 pt-3">
                    <h3 className="text-xs font-semibold text-gray-700 dark:text-gray-300 mb-2">
                        監視中（{artists.length} 件）
                    </h3>
                    {loading ? (
                        <div className="flex items-center justify-center py-4 text-gray-400">
                            <Loader2 className="w-5 h-5 animate-spin" />
                        </div>
                    ) : error ? (
                        <p className="text-xs text-red-500 dark:text-red-400">{error}</p>
                    ) : artists.length === 0 ? (
                        <p className="text-xs text-gray-500 dark:text-gray-400 py-2">
                            監視対象が登録されていません。
                        </p>
                    ) : (
                        <ul className="space-y-1 max-h-64 overflow-y-auto">
                            {artists.map((entry) => (
                                <li
                                    key={`${entry.normalized}:${entry.language}`}
                                    className="flex items-center gap-2 px-2 py-1.5 rounded-md bg-gray-50 dark:bg-gray-800"
                                >
                                    <div className="flex-1 min-w-0">
                                        <div className="text-sm text-gray-900 dark:text-gray-100 truncate">
                                            {entry.display_name}
                                        </div>
                                        <div className="text-xs text-gray-500 dark:text-gray-400">
                                            {entry.language} / 追加: {entry.added_at}
                                        </div>
                                    </div>
                                    <button
                                        onClick={() => setConfirmTarget(entry)}
                                        className="p-1 rounded text-gray-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/30 transition-colors"
                                        title="削除"
                                    >
                                        <Trash2 className="w-4 h-4" />
                                    </button>
                                </li>
                            ))}
                        </ul>
                    )}
                </div>
            </DialogBody>
            <DialogFooter>
                <DialogCancelButton onClick={onClose}>閉じる</DialogCancelButton>
            </DialogFooter>

            <ConfirmDialog
                open={confirmTarget !== null}
                title="監視対象を削除"
                message={
                    confirmTarget
                        ? `「${confirmTarget.display_name}」(${confirmTarget.language}) を監視対象から削除します。\nよろしいですか？`
                        : ''
                }
                confirmLabel="削除"
                danger
                onConfirm={handleConfirmRemove}
                onCancel={() => setConfirmTarget(null)}
            />
        </Dialog>
    );
}
