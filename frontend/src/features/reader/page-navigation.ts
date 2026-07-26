import type { ReadingDirection } from '@/types';

export interface PageNavigationState {
    page: number;
    numPages: number;
    isSpread: boolean;
    direction: ReadingDirection;
}

export function normalizeReaderPage(
    page: number,
    numPages: number,
    isSpread: boolean,
    direction: ReadingDirection,
): number {
    const clamped = Math.max(1, Math.min(page, Math.max(1, numPages)));
    if (!isSpread) return clamped;
    if (direction === 'rtl') {
        if (clamped === 1) return 1;
        return clamped % 2 === 0 ? clamped : clamped - 1;
    }
    return clamped % 2 === 1 ? clamped : Math.max(1, clamped - 1);
}

export function nextReaderPage({
    page,
    numPages,
    isSpread,
    direction,
}: PageNavigationState): number | null {
    if (!isSpread) return page < numPages ? page + 1 : null;
    if (direction === 'rtl') {
        if (page === 1) return page + 1 <= numPages ? 2 : null;
        return page + 2 <= numPages ? page + 2 : null;
    }
    if (page + 2 <= numPages) return page + 2;
    return page + 1 <= numPages ? page + 1 : null;
}

export function previousReaderPage({
    page,
    numPages: _numPages,
    isSpread,
    direction,
}: PageNavigationState): number | null {
    if (!isSpread) return page > 1 ? page - 1 : null;
    if (direction === 'rtl') {
        if (page === 2) return 1;
        return page > 2 ? page - 2 : null;
    }
    if (page > 2) return page - 2;
    return page === 2 ? 1 : null;
}
