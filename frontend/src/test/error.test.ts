import { describe, it, expect } from 'vitest';
import { errorMessage } from '../utils/error';

describe('errorMessage', () => {
    it('Error インスタンスは message を返す', () => {
        expect(errorMessage(new Error('boom'), 'fallback')).toBe('boom');
    });

    it('Error 派生（TypeError）も message を返す', () => {
        expect(errorMessage(new TypeError('type'), 'fallback')).toBe('type');
    });

    it('文字列は Error ではないので fallback を返す', () => {
        expect(errorMessage('plain string', 'fallback')).toBe('fallback');
    });

    it('数値は fallback を返す', () => {
        expect(errorMessage(42, 'fallback')).toBe('fallback');
    });

    it('null は fallback を返す', () => {
        expect(errorMessage(null, 'fallback')).toBe('fallback');
    });

    it('undefined は fallback を返す', () => {
        expect(errorMessage(undefined, 'fallback')).toBe('fallback');
    });

    it('object（Error でない）は fallback を返す', () => {
        expect(errorMessage({ message: 'fake' }, 'fallback')).toBe('fallback');
    });

    it('Error の message が空文字でもそれを返す', () => {
        expect(errorMessage(new Error(''), 'fallback')).toBe('');
    });
});
