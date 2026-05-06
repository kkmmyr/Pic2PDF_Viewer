import { useState, useEffect, useCallback } from 'react';
import type { LibrarySource } from '../types';
import { STORAGE_KEYS } from '../constants';
import { getStorageJson, setStorageJson } from '../utils/storage';

/** groupId → ピン留めされた book_name。1グループにつき1冊のみ */
export type PinsMap = Record<string, string>;

const EMPTY_PINS: PinsMap = {};

/**
 * シリーズ/作者集約カードの代表ピン管理。
 *
 * - seriesPins: series_id → book_name
 * - authorPins: 作者キー（ソート済み作者名を '\n' 結合）→ book_name
 * - ソース切り替え時に該当ソースのデータを再ロードする
 */
export function useLibraryPins(source: LibrarySource) {
    const seriesKey = `${STORAGE_KEYS.SERIES_PINS_PREFIX}${source}`;
    const authorKey = `${STORAGE_KEYS.AUTHOR_PINS_PREFIX}${source}`;

    const [seriesPins, setSeriesPins] = useState<PinsMap>(() =>
        getStorageJson<PinsMap>(seriesKey, EMPTY_PINS),
    );
    const [authorPins, setAuthorPins] = useState<PinsMap>(() =>
        getStorageJson<PinsMap>(authorKey, EMPTY_PINS),
    );

    useEffect(() => {
        setSeriesPins(getStorageJson<PinsMap>(seriesKey, EMPTY_PINS));
        setAuthorPins(getStorageJson<PinsMap>(authorKey, EMPTY_PINS));
    }, [seriesKey, authorKey]);

    const toggleSeriesPin = useCallback(
        (seriesId: string, bookName: string) => {
            setSeriesPins((prev) => {
                const next = { ...prev };
                if (prev[seriesId] === bookName) {
                    delete next[seriesId];
                } else {
                    next[seriesId] = bookName;
                }
                setStorageJson(seriesKey, next);
                return next;
            });
        },
        [seriesKey],
    );

    const toggleAuthorPin = useCallback(
        (authorGroupId: string, bookName: string) => {
            setAuthorPins((prev) => {
                const next = { ...prev };
                if (prev[authorGroupId] === bookName) {
                    delete next[authorGroupId];
                } else {
                    next[authorGroupId] = bookName;
                }
                setStorageJson(authorKey, next);
                return next;
            });
        },
        [authorKey],
    );

    return { seriesPins, authorPins, toggleSeriesPin, toggleAuthorPin };
}
