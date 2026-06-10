import { renderHook, act } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { useDialogToggles } from '../hooks/library/useDialogToggles';

type Key = 'rename' | 'delete' | 'merge';

describe('useDialogToggles', () => {
    it('初期状態は全部 isOpen=false', () => {
        const { result } = renderHook(() => useDialogToggles<Key>());
        expect(result.current.isOpen('rename')).toBe(false);
        expect(result.current.isOpen('delete')).toBe(false);
        expect(result.current.isOpen('merge')).toBe(false);
    });

    it('open(key) で対象キーが isOpen=true', () => {
        const { result } = renderHook(() => useDialogToggles<Key>());
        act(() => result.current.open('rename'));
        expect(result.current.isOpen('rename')).toBe(true);
        expect(result.current.isOpen('delete')).toBe(false);
    });

    it('別キーを open すると排他的に切り替わる（前のキーは閉じる）', () => {
        const { result } = renderHook(() => useDialogToggles<Key>());
        act(() => result.current.open('rename'));
        act(() => result.current.open('delete'));
        expect(result.current.isOpen('rename')).toBe(false);
        expect(result.current.isOpen('delete')).toBe(true);
    });

    it('close() で全キーが閉じる', () => {
        const { result } = renderHook(() => useDialogToggles<Key>());
        act(() => result.current.open('merge'));
        act(() => result.current.close());
        expect(result.current.isOpen('merge')).toBe(false);
        expect(result.current.isOpen('rename')).toBe(false);
    });

    it('閉じた状態で close() を呼んでも問題なし', () => {
        const { result } = renderHook(() => useDialogToggles<Key>());
        act(() => result.current.close());
        expect(result.current.isOpen('rename')).toBe(false);
    });

    it('同じキーを 2 回 open しても挙動は変わらない（idempotent）', () => {
        const { result } = renderHook(() => useDialogToggles<Key>());
        act(() => result.current.open('rename'));
        act(() => result.current.open('rename'));
        expect(result.current.isOpen('rename')).toBe(true);
    });
});
