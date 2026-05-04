import { useState, useEffect } from 'react';
import { Dialog, DialogBody, DialogFooter, DialogCancelButton, DialogPrimaryButton } from '../ui/Dialog';
import { useDialogSubmit } from '../../hooks/useDialogSubmit';

interface SeriesEditDialogProps {
    open: boolean;
    /** 対象書籍のファイル名（タイトル表示用） */
    targetName: string;
    /** 現在のシリーズ情報。null ならシリーズ未割当 */
    current: { id: string; title: string; index: number } | null;
    /** このソースの既存シリーズ一覧（id 重複排除済み） */
    allSeries: { id: string; title: string }[];
    onClose: () => void;
    /** 既存または新規シリーズに割り当てる */
    onAssign: (params: { title: string; index: number; id?: string }) => Promise<void>;
    /** シリーズから外す */
    onUnassign: () => Promise<void>;
}

type Mode = 'existing' | 'new' | 'unassign';

/**
 * 書籍のシリーズ手動編集ダイアログ。
 * - 既存シリーズに追加（id を引き継ぐ）
 * - 新規シリーズを作成
 * - シリーズから外す
 */
export function SeriesEditDialog({
    open, targetName, current, allSeries, onClose, onAssign, onUnassign,
}: SeriesEditDialogProps) {
    const [mode, setMode] = useState<Mode>(current ? 'existing' : 'new');
    const [selectedId, setSelectedId] = useState<string>(current?.id ?? '');
    const [newTitle, setNewTitle] = useState<string>('');
    const [indexStr, setIndexStr] = useState<string>(current?.index ? String(current.index) : '1');
    const { saving, error, setError, handleSubmit } = useDialogSubmit(onClose, '保存に失敗しました。');

    useEffect(() => {
        if (!open) return;
        setMode(current ? 'existing' : 'new');
        setSelectedId(current?.id ?? (allSeries[0]?.id ?? ''));
        setNewTitle('');
        setIndexStr(current?.index !== undefined ? String(current.index) : '1');
        setError(null);
    }, [open, current, allSeries, setError]);

    const handleSubmitWrapper = () => {
        handleSubmit(async () => {
            if (mode === 'unassign') {
                await onUnassign();
            } else {
                const idx = Number(indexStr);
                if (!Number.isFinite(idx) || idx <= 0) {
                    throw new Error('巻数は正の数値を入力してください（小数も可）。');
                }
                if (mode === 'existing') {
                    if (!selectedId) throw new Error('既存シリーズを選択してください。');
                    const series = allSeries.find(s => s.id === selectedId);
                    if (!series) throw new Error('選択したシリーズが見つかりません。');
                    await onAssign({ title: series.title, index: idx, id: selectedId });
                } else {
                    if (!newTitle.trim()) throw new Error('新規シリーズのタイトルを入力してください。');
                    await onAssign({ title: newTitle.trim(), index: idx });
                }
            }
        });
    };

    const noExistingSeries = allSeries.length === 0;

    return (
        <Dialog
            open={open}
            title="シリーズを編集"
            subtitle={targetName.replace(/\.pdf$/i, '')}
            onClose={onClose}
            maxWidth="md"
        >
            <DialogBody>
                {current && (
                    <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
                        現在: <span className="font-medium">{current.title}</span> #{current.index}
                    </p>
                )}

                <div className="space-y-3">
                    <label className="flex items-start gap-2 cursor-pointer">
                        <input
                            type="radio"
                            name="mode"
                            checked={mode === 'existing'}
                            onChange={() => setMode('existing')}
                            disabled={noExistingSeries}
                            className="mt-1 accent-accent-600"
                        />
                        <div className="flex-1">
                            <div className="text-sm font-medium text-gray-800 dark:text-gray-200">
                                既存のシリーズに追加
                                {noExistingSeries && <span className="ml-2 text-xs text-gray-400">（このソースに既存シリーズなし）</span>}
                            </div>
                            {mode === 'existing' && (
                                <select
                                    value={selectedId}
                                    onChange={(e) => setSelectedId(e.target.value)}
                                    disabled={noExistingSeries}
                                    className="mt-1 w-full px-2 py-1 border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-sm text-gray-800 dark:text-gray-200"
                                >
                                    {allSeries.map(s => (
                                        <option key={s.id} value={s.id}>{s.title}</option>
                                    ))}
                                </select>
                            )}
                        </div>
                    </label>

                    <label className="flex items-start gap-2 cursor-pointer">
                        <input
                            type="radio"
                            name="mode"
                            checked={mode === 'new'}
                            onChange={() => setMode('new')}
                            className="mt-1 accent-accent-600"
                        />
                        <div className="flex-1">
                            <div className="text-sm font-medium text-gray-800 dark:text-gray-200">
                                新規シリーズを作成
                            </div>
                            {mode === 'new' && (
                                <input
                                    type="text"
                                    value={newTitle}
                                    onChange={(e) => setNewTitle(e.target.value)}
                                    placeholder="シリーズタイトル"
                                    className="mt-1 w-full px-2 py-1 border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-sm text-gray-800 dark:text-gray-200"
                                />
                            )}
                        </div>
                    </label>

                    {mode !== 'unassign' && (
                        <div className="pl-6">
                            <label className="text-sm text-gray-700 dark:text-gray-300">
                                巻数 <span className="text-xs text-gray-500">（小数可、例: 2.5）</span>
                            </label>
                            <input
                                type="number"
                                step="0.1"
                                min="0.1"
                                value={indexStr}
                                onChange={(e) => setIndexStr(e.target.value)}
                                className="mt-1 w-32 px-2 py-1 border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-sm text-gray-800 dark:text-gray-200"
                            />
                        </div>
                    )}

                    {current && (
                        <label className="flex items-start gap-2 cursor-pointer pt-2 border-t border-gray-200 dark:border-gray-700">
                            <input
                                type="radio"
                                name="mode"
                                checked={mode === 'unassign'}
                                onChange={() => setMode('unassign')}
                                className="mt-1 accent-red-600"
                            />
                            <div className="flex-1">
                                <div className="text-sm font-medium text-red-600 dark:text-red-400">
                                    シリーズから外す
                                </div>
                                <p className="text-xs text-gray-500 dark:text-gray-400">
                                    series_id / series_title / series_index を削除します（書籍ファイルや他メタは保持）。
                                </p>
                            </div>
                        </label>
                    )}
                </div>

                {error && (
                    <p className="mt-3 text-xs text-red-500 dark:text-red-400">{error}</p>
                )}
            </DialogBody>
            <DialogFooter>
                <DialogCancelButton onClick={onClose} disabled={saving} />
                <DialogPrimaryButton onClick={handleSubmitWrapper} disabled={saving}>
                    {saving ? '保存中...' : '適用'}
                </DialogPrimaryButton>
            </DialogFooter>
        </Dialog>
    );
}
