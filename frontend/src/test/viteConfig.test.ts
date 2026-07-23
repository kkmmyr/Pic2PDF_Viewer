import { describe, expect, it } from 'vitest';

import { resolveManualChunk } from '@/config/buildChunks';

describe('Vite production chunking', () => {
    it('leaves dnd-kit to automatic chunking to avoid a circular bootstrap', () => {
        expect(
            resolveManualChunk('C:/repo/node_modules/@dnd-kit/core/dist/index.js'),
        ).toBeUndefined();
    });

    it('does not force general dependencies into a shared vendor chunk', () => {
        expect(resolveManualChunk('C:/repo/node_modules/react/index.js')).toBeUndefined();
        expect(resolveManualChunk('C:/repo/node_modules/axios/index.js')).toBeUndefined();
    });
});
