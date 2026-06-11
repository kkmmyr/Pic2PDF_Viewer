import { useEffect, useState } from 'react';

import { useDialogSubmit } from '@/hooks/library/useDialogSubmit';
import type { BookSummary, SeriesSummary } from '@/features/novel_db/types';
import {
    Dialog,
    DialogBody,
    DialogCancelButton,
    DialogFooter,
    DialogPrimaryButton,
} from '@/components/ui/dialog';
import { SearchableSelect } from '@/components/ui/searchable-select';

interface Props {
    open: boolean;
    /** 登録対象（選択順。この順に巻番号が振られる） */
    selectedBooks: BookSummary[];
    /** 既存シリーズ一覧 */
    allSeries: SeriesSummary[];
    /** 全書籍一覧（既存シリーズの最大巻番号を算出するために使用） */
    allBooks: BookSummary[];
    onClose: () => void;
    /**
     * 一括登録を実行する。
     * - mode='existing'/'new': series_id と各書籍の volume を設定
     * - mode='remove': series_id をクリア
     */
    onAssign: (params: {
        mode: 'existing' | 'new' | 'remove';
        seriesId?: string;
        seriesTitle?: string;
        volumes?: number[];
    }) => Promise<void>;
}

type Mode = 'existing' | 'new' | 'remove';

/** series_id に属する書籍の最大 volume（なければ 0）を返す。 */
function maxVolumeForSeries(seriesId: string, allBooks: BookSummary[]): number {
    let max = 0;
    for (const b of allBooks) {
        if (b.series_id === seriesId && b.volume !== null && b.volume > max) {
            max = b.volume;
        }
    }
    return max;
}

/**
 * 小説 DB 用: 複数冊をシリーズに一括登録するダイアログ（B-21）。
 * 巻番号は選択順に自動採番（既存追加なら max+1 から、新規なら 1 から）。
 */
export function NovelBulkSeriesAssignDialog({
    open,
    selectedBooks,
    allSeries,
    allBooks,
    onClose,
    onAssign,
}: Props) {
    const noExisting = allSeries.length === 0;
    const [mode, setMode] = useState<Mode>(noExisting ? 'new' : 'existing');
    const [selectedSeriesId, setSelectedSeriesId] = useState<string>('');
    const [newTitle, setNewTitle] = useState('');
    const { saving, error, handleSubmit } = useDialogSubmit(onClose, '登録に失敗しました。');

    useEffect(() => {
        if (!open) return;
        setMode(noExisting ? 'new' : 'existing');
        setSelectedSeriesId(allSeries[0]?.id ?? '');
        setNewTitle('');
    }, [open, noExisting, allSeries]);

    const selectedSeries = allSeries.find((s) => s.id === selectedSeriesId);
    const startVolume =
        mode === 'existing' && selectedSeries
            ? maxVolumeForSeries(selectedSeries.id, allBooks) + 1
            : 1;
    const previewVolumes = selectedBooks.map((_, i) => startVolume + i);

    const seriesTitles = allSeries.map((s) => s.name);
    const selectedTitle = selectedSeries?.name ?? '';

    const handleSeriesChange = (name: string) => {
        const found = allSeries.find((s) => s.name === name);
        setSelectedSeriesId(found?.id ?? '');
    };

    const handleSubmitWrapper = () => {
        handleSubmit(async () => {
            if (mode === 'remove') {
                await onAssign({ mode: 'remove' });
            } else if (mode === 'existing') {
                if (!selectedSeries) throw new Error('既存シリーズを選択してください。');
                await onAssign({
                    mode: 'existing',
                    seriesId: selectedSeries.id,
                    seriesTitle: selectedSeries.name,
                    volumes: previewVolumes,
                });
            } else {
                if (!newTitle.trim()) throw new Error('シリーズタイトルを入力してください。');
                await onAssign({
                    mode: 'new',
                    seriesId: newTitle.trim(),
                    seriesTitle: newTitle.trim(),
                    volumes: previewVolumes,
                });
            }
        });
    };

    return (
        <Dialog
            open={open}
            title="シリーズに一括登録"
            subtitle={`${selectedBooks.length} 冊を選択順に登録します`}
            onClose={onClose}
            maxWidth="md"
            nested
        >
            <DialogBody>
                <div className="space-y-3 mb-4">
                    {/* 既存シリーズに追加 */}
                    <label className="flex items-start gap-2 cursor-pointer">
                        <input
                            type="radio"
                            name="novel-series-mode"
                            checked={mode === 'existing'}
                            onChange={() => setMode('existing')}
                            disabled={noExisting}
                            className="mt-1 accent-primary-600"
                        />
                        <div className="flex-1">
                            <div className="text-sm font-medium text-gray-800 dark:text-gray-200">
                                既存のシリーズに追加
                                {noExisting && (
                                    <span className="ml-2 text-xs text-gray-400">
                                        （既存シリーズなし）
                                    </span>
                                )}
                            </div>
                            {mode === 'existing' && !noExisting && (
                                <div className="mt-1.5">
                                    <SearchableSelect
                                        value={selectedTitle}
                                        options={seriesTitles}
                                        emptyLabel="シリーズを選択..."
                                        placeholder="シリーズ名で絞り込み"
                                        onChange={handleSeriesChange}
                                    />
                                    {selectedSeries && (
                                        <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
                                            現在の最大巻:{' '}
                                            {maxVolumeForSeries(selectedSeries.id, allBooks)}
                                        </p>
                                    )}
                                </div>
                            )}
                        </div>
                    </label>

                    {/* 新規シリーズを作成 */}
                    <label className="flex items-start gap-2 cursor-pointer">
                        <input
                            type="radio"
                            name="novel-series-mode"
                            checked={mode === 'new'}
                            onChange={() => setMode('new')}
                            className="mt-1 accent-primary-600"
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
                                    className="mt-1 w-full px-2 py-1 border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-sm text-gray-800 dark:text-gray-200 focus:outline-none focus:ring-2 focus:ring-primary-500"
                                />
                            )}
                        </div>
                    </label>

                    {/* シリーズから外す */}
                    <label className="flex items-start gap-2 cursor-pointer">
                        <input
                            type="radio"
                            name="novel-series-mode"
                            checked={mode === 'remove'}
                            onChange={() => setMode('remove')}
                            className="mt-1 accent-primary-600"
                        />
                        <div className="flex-1">
                            <div className="text-sm font-medium text-gray-800 dark:text-gray-200">
                                シリーズから外す
                            </div>
                            {mode === 'remove' && (
                                <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                                    選択した書籍のシリーズ設定・巻番号をすべてクリアします。
                                </p>
                            )}
                        </div>
                    </label>
                </div>

                {/* 登録プレビュー（remove 以外） */}
                {mode !== 'remove' && (
                    <div className="mb-1">
                        <p className="text-sm text-gray-500 dark:text-gray-400 mb-2">
                            登録順（{previewVolumes[0] ?? '?'} 巻から）:
                        </p>
                        <ul className="text-sm text-gray-700 dark:text-gray-300 space-y-1 max-h-40 overflow-y-auto border border-gray-200 dark:border-gray-700 rounded-lg p-2 bg-gray-50 dark:bg-gray-900">
                            {selectedBooks.map((book, i) => (
                                <li key={book.name} className="flex items-center gap-2">
                                    <span className="text-primary-600 dark:text-primary-400 tabular-nums w-10 text-right shrink-0 font-medium">
                                        {previewVolumes[i]}巻
                                    </span>
                                    <span className="truncate">{book.name}</span>
                                </li>
                            ))}
                        </ul>
                    </div>
                )}

                {error && <p className="mt-3 text-xs text-red-500 dark:text-red-400">{error}</p>}
            </DialogBody>
            <DialogFooter>
                <DialogCancelButton onClick={onClose} disabled={saving} />
                <DialogPrimaryButton onClick={handleSubmitWrapper} disabled={saving}>
                    {saving ? '保存中...' : mode === 'remove' ? 'シリーズから外す' : '登録'}
                </DialogPrimaryButton>
            </DialogFooter>
        </Dialog>
    );
}
