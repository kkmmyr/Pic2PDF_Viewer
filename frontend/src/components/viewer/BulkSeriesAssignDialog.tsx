import { useState, useEffect } from 'react';
import { Dialog, DialogBody, DialogFooter, DialogCancelButton, DialogPrimaryButton } from '../ui/Dialog';
import type { ExistingSeriesOption } from '../../types';

export type { ExistingSeriesOption };

interface BulkSeriesAssignDialogProps {
    open: boolean;
    /** 登録対象（選択順、巻数の若い順に番号が振られる） */
    selectedNames: string[];
    /** 既存シリーズ一覧。空配列なら「既存に追加」モードは無効 */
    existingSeries: ExistingSeriesOption[];
    onClose: () => void;
    /**
     * 一括登録を実行する。
     * - id を渡せば既存シリーズに追加。`indexes` は max+1 から連番
     * - id 未指定なら新規作成。`indexes` は 1 から連番
     */
    onAssign: (params: { title: string; indexes: number[]; id?: string }) => Promise<void>;
}

type Mode = 'existing' | 'new';

/**
 * 複数書籍を 1 度にシリーズへ登録するダイアログ。
 * 巻数は **選択順** に自動採番（既存追加なら max+1 から、新規なら 1 から）。
 */
export function BulkSeriesAssignDialog({
    open, selectedNames, existingSeries, onClose, onAssign,
}: BulkSeriesAssignDialogProps) {
    const [mode, setMode] = useState<Mode>(existingSeries.length > 0 ? 'existing' : 'new');
    const [selectedId, setSelectedId] = useState<string>('');
    const [newTitle, setNewTitle] = useState<string>('');
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (!open) return;
        const fallbackMode: Mode = existingSeries.length > 0 ? 'existing' : 'new';
        setMode(fallbackMode);
        setSelectedId(existingSeries[0]?.id ?? '');
        setNewTitle('');
        setError(null);
    }, [open, existingSeries]);

    const noExistingSeries = existingSeries.length === 0;
    const selected = existingSeries.find(s => s.id === selectedId);

    // プレビュー表示用の巻数リスト
    const previewIndexes: number[] = (() => {
        const start = mode === 'existing' && selected
            ? Math.floor(selected.maxIndex) + 1
            : 1;
        return selectedNames.map((_, i) => start + i);
    })();

    const handleSubmit = async () => {
        setError(null);
        setSaving(true);
        try {
            if (mode === 'existing') {
                if (!selectedId || !selected) throw new Error('既存シリーズを選択してください。');
                await onAssign({
                    title: selected.title,
                    indexes: previewIndexes,
                    id: selectedId,
                });
            } else {
                if (!newTitle.trim()) throw new Error('シリーズタイトルを入力してください。');
                await onAssign({
                    title: newTitle.trim(),
                    indexes: previewIndexes,
                });
            }
            onClose();
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : '登録に失敗しました。');
        } finally {
            setSaving(false);
        }
    };

    const subtitle = `${selectedNames.length} 冊を選択順に登録します`;

    return (
        <Dialog
            open={open}
            title="シリーズに一括登録"
            subtitle={subtitle}
            onClose={onClose}
            maxWidth="md"
        >
            <DialogBody>
                <div className="space-y-3 mb-4">
                    <label className="flex items-start gap-2 cursor-pointer">
                        <input
                            type="radio"
                            name="mode"
                            checked={mode === 'existing'}
                            onChange={() => setMode('existing')}
                            disabled={noExistingSeries}
                            className="mt-1 accent-purple-600"
                        />
                        <div className="flex-1">
                            <div className="text-sm font-medium text-gray-800 dark:text-gray-200">
                                既存のシリーズに追加
                                {noExistingSeries && (
                                    <span className="ml-2 text-xs text-gray-400">（このソースに既存シリーズなし）</span>
                                )}
                            </div>
                            {mode === 'existing' && (
                                <select
                                    value={selectedId}
                                    onChange={(e) => setSelectedId(e.target.value)}
                                    disabled={noExistingSeries}
                                    className="mt-1 w-full px-2 py-1 border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-sm text-gray-800 dark:text-gray-200"
                                >
                                    {existingSeries.map(s => (
                                        <option key={s.id} value={s.id}>
                                            {s.title}（現在の最大巻: {s.maxIndex}）
                                        </option>
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
                            className="mt-1 accent-purple-600"
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
                </div>

                {/* 採番プレビュー */}
                <div className="mb-1">
                    <p className="text-sm text-gray-500 dark:text-gray-400 mb-2">
                        登録順 (上から #{previewIndexes[0] ?? '?'} 巻):
                    </p>
                    <ul className="text-sm text-gray-700 dark:text-gray-300 space-y-1 max-h-40 overflow-y-auto border border-gray-200 dark:border-gray-700 rounded-lg p-2 bg-gray-50 dark:bg-gray-900">
                        {selectedNames.map((name, i) => (
                            <li key={name} className="flex items-center gap-2">
                                <span className="text-purple-600 dark:text-purple-400 tabular-nums w-10 text-right shrink-0 font-medium">
                                    #{previewIndexes[i]}
                                </span>
                                <span className="truncate">{name.replace(/\.pdf$/i, '')}</span>
                            </li>
                        ))}
                    </ul>
                </div>

                {error && (
                    <p className="mt-3 text-xs text-red-500 dark:text-red-400">{error}</p>
                )}
            </DialogBody>
            <DialogFooter>
                <DialogCancelButton onClick={onClose} disabled={saving} />
                <DialogPrimaryButton onClick={handleSubmit} disabled={saving}>
                    {saving ? '登録中...' : '登録'}
                </DialogPrimaryButton>
            </DialogFooter>
        </Dialog>
    );
}
