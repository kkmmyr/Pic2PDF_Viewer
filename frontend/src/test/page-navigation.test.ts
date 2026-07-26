import { describe, expect, it } from 'vitest';

import {
    nextReaderPage,
    normalizeReaderPage,
    previousReaderPage,
} from '@/features/reader/page-navigation';

describe.each([
    ['single first', false, 'ltr', 1, 5, 2, null],
    ['single last', false, 'ltr', 5, 5, null, 4],
    ['RTL cover', true, 'rtl', 1, 5, 2, null],
    ['RTL spread', true, 'rtl', 2, 5, 4, 1],
    ['RTL final odd', true, 'rtl', 4, 5, null, 2],
    ['LTR first spread', true, 'ltr', 1, 5, 3, null],
    ['LTR spread', true, 'ltr', 3, 5, 5, 1],
    ['LTR final single page', true, 'ltr', 3, 4, 4, 1],
    ['LTR end', true, 'ltr', 4, 4, null, 2],
] as const)('%s navigation', (_label, isSpread, direction, page, numPages, next, previous) => {
    const state = { page, numPages, isSpread, direction };

    it(`next is ${String(next)}`, () => {
        expect(nextReaderPage(state)).toBe(next);
    });

    it(`previous is ${String(previous)}`, () => {
        expect(previousReaderPage(state)).toBe(previous);
    });
});

describe.each([
    [false, 'ltr', 0, 1],
    [false, 'ltr', 12, 10],
    [true, 'rtl', 1, 1],
    [true, 'rtl', 5, 4],
    [true, 'ltr', 4, 3],
    [true, 'ltr', 10, 9],
] as const)('normalizeReaderPage', (isSpread, direction, input, expected) => {
    it(`${direction} spread=${String(isSpread)}: ${input} -> ${expected}`, () => {
        expect(normalizeReaderPage(input, 10, isSpread, direction)).toBe(expected);
    });
});
