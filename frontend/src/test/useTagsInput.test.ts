import { renderHook, act } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { useTagsInput } from '@/hooks/useTagsInput';

const makeKey = (key: string): React.KeyboardEvent<HTMLInputElement> => {
    const e = {
        key,
        preventDefault: () => {},
    } as unknown as React.KeyboardEvent<HTMLInputElement>;
    return e;
};

describe('useTagsInput', () => {
    it('初期状態は tags=[] / input=""', () => {
        const { result } = renderHook(() => useTagsInput());
        expect(result.current.tags).toEqual([]);
        expect(result.current.input).toBe('');
    });

    it('initialTags を反映する', () => {
        const { result } = renderHook(() => useTagsInput(['A', 'B']));
        expect(result.current.tags).toEqual(['A', 'B']);
    });

    describe('addTag', () => {
        it('値を trim して追加する', () => {
            const { result } = renderHook(() => useTagsInput());
            act(() => result.current.addTag('  hello  '));
            expect(result.current.tags).toEqual(['hello']);
        });

        it('空文字 / 空白のみは追加しない', () => {
            const { result } = renderHook(() => useTagsInput());
            act(() => result.current.addTag(''));
            act(() => result.current.addTag('   '));
            expect(result.current.tags).toEqual([]);
        });

        it('重複は無視する', () => {
            const { result } = renderHook(() => useTagsInput(['A']));
            act(() => result.current.addTag('A'));
            expect(result.current.tags).toEqual(['A']);
        });

        it('addTag 後に input は空に戻る', () => {
            const { result } = renderHook(() => useTagsInput());
            act(() => result.current.setInput('X'));
            act(() => result.current.addTag('Y'));
            expect(result.current.input).toBe('');
        });
    });

    describe('removeTag', () => {
        it('指定 index を削除する', () => {
            const { result } = renderHook(() => useTagsInput(['A', 'B', 'C']));
            act(() => result.current.removeTag(1));
            expect(result.current.tags).toEqual(['A', 'C']);
        });
    });

    describe('handleKeyDown', () => {
        it('Enter で input が addTag される', () => {
            const { result } = renderHook(() => useTagsInput());
            act(() => result.current.setInput('hello'));
            act(() => result.current.handleKeyDown(makeKey('Enter')));
            expect(result.current.tags).toEqual(['hello']);
            expect(result.current.input).toBe('');
        });

        it('","（カンマ）でも addTag される', () => {
            const { result } = renderHook(() => useTagsInput());
            act(() => result.current.setInput('foo'));
            act(() => result.current.handleKeyDown(makeKey(',')));
            expect(result.current.tags).toEqual(['foo']);
        });

        it('Backspace + input="" + tags 非空 で末尾を削除', () => {
            const { result } = renderHook(() => useTagsInput(['A', 'B']));
            act(() => result.current.handleKeyDown(makeKey('Backspace')));
            expect(result.current.tags).toEqual(['A']);
        });

        it('Backspace + input 非空 では削除しない', () => {
            const { result } = renderHook(() => useTagsInput(['A']));
            act(() => result.current.setInput('x'));
            act(() => result.current.handleKeyDown(makeKey('Backspace')));
            expect(result.current.tags).toEqual(['A']);
        });

        it('Backspace + tags 空 では何もしない', () => {
            const { result } = renderHook(() => useTagsInput());
            act(() => result.current.handleKeyDown(makeKey('Backspace')));
            expect(result.current.tags).toEqual([]);
        });

        it('Enter で空文字なら何もしない', () => {
            const { result } = renderHook(() => useTagsInput());
            act(() => result.current.handleKeyDown(makeKey('Enter')));
            expect(result.current.tags).toEqual([]);
        });
    });

    describe('handleBlur', () => {
        it('input に値があれば addTag', () => {
            const { result } = renderHook(() => useTagsInput());
            act(() => result.current.setInput('blur-add'));
            act(() => result.current.handleBlur());
            expect(result.current.tags).toEqual(['blur-add']);
        });

        it('input が空白のみなら何もしない', () => {
            const { result } = renderHook(() => useTagsInput());
            act(() => result.current.setInput('   '));
            act(() => result.current.handleBlur());
            expect(result.current.tags).toEqual([]);
        });
    });

    describe('getFinalTags', () => {
        it('input に未確定値があれば結合 + 重複排除して返す', () => {
            const { result } = renderHook(() => useTagsInput(['A']));
            act(() => result.current.setInput('B'));
            expect(result.current.getFinalTags()).toEqual(['A', 'B']);
        });

        it('input が空なら tags そのまま', () => {
            const { result } = renderHook(() => useTagsInput(['A', 'B']));
            expect(result.current.getFinalTags()).toEqual(['A', 'B']);
        });

        it('input が既存 tag と重複なら tags のまま', () => {
            const { result } = renderHook(() => useTagsInput(['A']));
            act(() => result.current.setInput('A'));
            expect(result.current.getFinalTags()).toEqual(['A']);
        });
    });

    describe('reset', () => {
        it('引数なしで全部空にリセット', () => {
            const { result } = renderHook(() => useTagsInput(['A']));
            act(() => result.current.setInput('x'));
            act(() => result.current.reset());
            expect(result.current.tags).toEqual([]);
            expect(result.current.input).toBe('');
        });

        it('引数で指定した値にリセット', () => {
            const { result } = renderHook(() => useTagsInput());
            act(() => result.current.reset(['X', 'Y']));
            expect(result.current.tags).toEqual(['X', 'Y']);
            expect(result.current.input).toBe('');
        });
    });
});
