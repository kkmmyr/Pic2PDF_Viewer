import { useEffect, useState } from 'react';
import {
    Dialog,
    DialogBody,
    DialogFooter,
    DialogCancelButton,
    DialogPrimaryButton,
} from '@/components/ui/dialog';
import { SearchableSelect } from '@/components/ui/searchable-select';
import type { ExistingSeriesOption, LibrarySource } from '@/types';
import { useDialogSubmit } from '@/hooks/library/useDialogSubmit';
import { useSeriesSuggestion } from '@/hooks/useSeriesSuggestion';

export interface BulkSeriesAssignResult {
    mode: 'existing' | 'new' | 'remove';
    seriesId?: string;
    seriesTitle?: string;
    indexes?: number[];
}

interface BulkSeriesAssignDialogProps {
    open: boolean;
    /** 登録対象（選択順、巻数の若い順に番号が振られる） */
    selectedNames: string[];
    /** 既存シリーズ一覧。空配列なら「既存に追加」モードは無効 */
    existingSeries: ExistingSeriesOption[];
    /** ネストダイアログとして上層に表示する場合 true（デフォルト false） */
    nested?: boolean;
    /** 「シリーズから外す」モードを有効にする（novel ソース用） */
    showRemoveMode?: boolean;
    /** AI 提案モードを有効にする（library ソース用） */
    source?: LibrarySource;
    path?: string;
    onClose: () => void;
    onAssign: (params: BulkSeriesAssignResult) => Promise<void>;
}

type Mode = 'existing' | 'new' | 'suggested' | 'remove';

/**
 * 複数書籍を 1 度にシリーズへ登録するダイアログ。
 * library（doujin/comic）と novel 両ソースで共用。
 * - `source`/`path` を渡すと AI 提案モードが有効になる
 * - `showRemoveMode=true` でシリーズ解除モードが有効になる
 */
export function BulkSeriesAssignDialog({
    open,
    selectedNames,
    existingSeries,
    nested = false,
    showRemoveMode = false,
    source,
    path,
    onClose,
    onAssign,
}: BulkSeriesAssignDialogProps) {
    const showSuggestedMode = Boolean(source && path);
    const noExistingSeries = existingSeries.length === 0;
    const [mode, setMode] = useState<Mode>(noExistingSeries ? 'new' : 'existing');
    const [selectedTitle, setSelectedTitle] = useState<string>('');
    const [newTitle, setNewTitle] = useState<string>('');
    const [selectedSuggestionId, setSelectedSuggestionId] = useState<string>('');
    const { saving, error, handleSubmit } = useDialogSubmit(onClose, '登録に失敗しました。');
    const {
        candidates,
        loading: suggestLoading,
        error: suggestError,
        fetchSuggestions,
        reset: resetSuggestions,
    } = useSeriesSuggestion(source ?? 'doujin', path ?? '');

    useEffect(() => {
        if (!open) {
            resetSuggestions();
            return;
        }
        const fallbackMode: Mode = existingSeries.length > 0 ? 'existing' : 'new';
        setMode(fallbackMode);
        setSelectedTitle(existingSeries[0]?.title ?? '');
        setNewTitle('');
        setSelectedSuggestionId('');
    }, [open, existingSeries, resetSuggestions]);

    useEffect(() => {
        if (!open || mode !== 'suggested') return;
        fetchSuggestions(selectedNames);
        setSelectedSuggestionId('');
    }, [open, mode, selectedNames, fetchSuggestions]);

    const seriesTitles = existingSeries.map((s) => s.title);
    const selected = existingSeries.find((s) => s.title === selectedTitle);
    const selectedSuggestion = candidates.find((c) => c.series_id === selectedSuggestionId);

    const previewIndexes: number[] = (() => {
        const start = (() => {
            if (mode === 'existing' && selected) return Math.floor(selected.maxIndex) + 1;
            if (mode === 'suggested' && selectedSuggestion)
                return Math.floor(selectedSuggestion.series_max_index) + 1;
            return 1;
        })();
        return selectedNames.map((_, i) => start + i);
    })();

    const handleSubmitWrapper = () => {
        handleSubmit(async () => {
            if (mode === 'remove') {
                await onAssign({ mode: 'remove' });
            } else if (mode === 'existing') {
                if (!selectedTitle || !selected)
                    throw new Error('既存シリーズを選択してください。');
                await onAssign({
                    mode: 'existing',
                    seriesId: selected.id,
                    seriesTitle: selected.title,
                    indexes: previewIndexes,
                });
            } else if (mode === 'suggested') {
                if (!selectedSuggestion)
                    throw new Error('提案された候補から 1 つを選択してください。');
                await onAssign({
                    mode: 'existing',
                    seriesId: selectedSuggestion.series_id,
                    seriesTitle: selectedSuggestion.series_title,
                    indexes: previewIndexes,
                });
            } else {
                if (!newTitle.trim()) throw new Error('シリーズタイトルを入力してください。');
                await onAssign({
                    mode: 'new',
                    seriesTitle: newTitle.trim(),
                    indexes: previewIndexes,
                });
            }
        });
    };

    return (
        <Dialog
            open={open}
            title="シリーズに一括登録"
            subtitle={`${selectedNames.length} 冊を選択順に登録します`}
            onClose={onClose}
            maxWidth="md"
            nested={nested}
        >
            <DialogBody>
                <div className="space-y-3 mb-4">
                    {/* 既存シリーズに追加 */}
                    <label className="flex items-start gap-2 cursor-pointer">
                        <input
                            type="radio"
                            name="bulk-series-mode"
                            checked={mode === 'existing'}
                            onChange={() => setMode('existing')}
                            disabled={noExistingSeries}
                            className="mt-1 accent-primary-600"
                        />
                        <div className="flex-1">
                            <div className="text-sm font-medium text-gray-800 dark:text-gray-200">
                                既存のシリーズに追加
                                {noExistingSeries && (
                                    <span className="ml-2 text-xs text-gray-400">
                                        （このソースに既存シリーズなし）
                                    </span>
                                )}
                            </div>
                            {mode === 'existing' && !noExistingSeries && (
                                <div className="mt-1.5">
                                    <SearchableSelect
                                        value={selectedTitle}
                                        options={seriesTitles}
                                        emptyLabel="シリーズを選択..."
                                        placeholder="シリーズタイトルで絞り込み"
                                        onChange={setSelectedTitle}
                                    />
                                    {selected && (
                                        <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
                                            現在の最大巻: {selected.maxIndex}
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
                            name="bulk-series-mode"
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
                                    className="mt-1 w-full px-2 py-1 border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-sm text-gray-800 dark:text-gray-200"
                                />
                            )}
                        </div>
                    </label>

                    {/* AI 提案モード（library ソース用） */}
                    {showSuggestedMode && (
                        <label className="flex items-start gap-2 cursor-pointer">
                            <input
                                type="radio"
                                name="bulk-series-mode"
                                checked={mode === 'suggested'}
                                onChange={() => setMode('suggested')}
                                disabled={noExistingSeries}
                                className="mt-1 accent-primary-600"
                            />
                            <div className="flex-1">
                                <div className="text-sm font-medium text-gray-800 dark:text-gray-200">
                                    AI が提案するシリーズに追加
                                    {noExistingSeries && (
                                        <span className="ml-2 text-xs text-gray-400">
                                            （このソースに既存シリーズなし）
                                        </span>
                                    )}
                                </div>
                                {mode === 'suggested' && !noExistingSeries && (
                                    <div className="mt-1.5 space-y-1.5">
                                        {suggestLoading && (
                                            <p className="text-xs text-gray-500 dark:text-gray-400">
                                                候補を取得中...
                                            </p>
                                        )}
                                        {suggestError && (
                                            <p className="text-xs text-red-500 dark:text-red-400">
                                                {suggestError}
                                            </p>
                                        )}
                                        {!suggestLoading &&
                                            !suggestError &&
                                            candidates.length === 0 && (
                                                <p className="text-xs text-gray-500 dark:text-gray-400">
                                                    マッチする既存シリーズが見つかりませんでした。
                                                </p>
                                            )}
                                        {candidates.map((c) => (
                                            <label
                                                key={c.series_id}
                                                className="flex items-start gap-2 cursor-pointer text-sm text-gray-700 dark:text-gray-300 px-2 py-1 rounded hover:bg-gray-50 dark:hover:bg-gray-800"
                                            >
                                                <input
                                                    type="radio"
                                                    name="suggestion"
                                                    checked={selectedSuggestionId === c.series_id}
                                                    onChange={() =>
                                                        setSelectedSuggestionId(c.series_id)
                                                    }
                                                    className="mt-1 accent-primary-600"
                                                />
                                                <div className="flex-1 min-w-0">
                                                    <div className="truncate">{c.series_title}</div>
                                                    <div className="text-xs text-gray-400 dark:text-gray-500 flex gap-2">
                                                        <span>スコア: {c.score.toFixed(2)}</span>
                                                        {c.reason.includes('author_match') && (
                                                            <span>同作者</span>
                                                        )}
                                                        <span>
                                                            現在の最大巻: {c.series_max_index}
                                                        </span>
                                                    </div>
                                                </div>
                                            </label>
                                        ))}
                                    </div>
                                )}
                            </div>
                        </label>
                    )}

                    {/* シリーズから外す（novel ソース用） */}
                    {showRemoveMode && (
                        <label className="flex items-start gap-2 cursor-pointer">
                            <input
                                type="radio"
                                name="bulk-series-mode"
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
                    )}
                </div>

                {/* 登録プレビュー（remove 以外） */}
                {mode !== 'remove' && (
                    <div className="mb-1">
                        <p className="text-sm text-gray-500 dark:text-gray-400 mb-2">
                            登録順 (上から #{previewIndexes[0] ?? '?'} 巻):
                        </p>
                        <ul className="text-sm text-gray-700 dark:text-gray-300 space-y-1 max-h-40 overflow-y-auto border border-gray-200 dark:border-gray-700 rounded-lg p-2 bg-gray-50 dark:bg-gray-900">
                            {selectedNames.map((name, i) => (
                                <li key={name} className="flex items-center gap-2">
                                    <span className="text-primary-600 dark:text-primary-400 tabular-nums w-10 text-right shrink-0 font-medium">
                                        #{previewIndexes[i]}
                                    </span>
                                    <span className="truncate">{name.replace(/\.pdf$/i, '')}</span>
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
                    {saving ? '登録中...' : mode === 'remove' ? 'シリーズから外す' : '登録'}
                </DialogPrimaryButton>
            </DialogFooter>
        </Dialog>
    );
}
