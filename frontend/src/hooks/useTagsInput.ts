import { useCallback, useRef, useState, KeyboardEvent } from 'react';

/**
 * chip 形式の複数値入力 UI で必要な state とイベントハンドラを共通化する。
 * 命名は歴史的経緯（タグ機能撤去後も汎用 chip UI として残置、`BulkAuthorDialog` で利用）。
 *
 * 利用側の使い方:
 *   const t = useTagsInput();
 *   <TagsInput
 *     tags={t.tags} input={t.input} inputRef={t.inputRef}
 *     onChange={t.setInput} onKeyDown={t.handleKeyDown}
 *     onRemove={t.removeTag} onBlur={t.handleBlur}
 *   />
 *   const submit = () => onApply(t.getFinalTags());
 */
export function useTagsInput(initialTags: string[] = []) {
    const [tags, setTags] = useState<string[]>(initialTags);
    const [input, setInput] = useState('');
    const inputRef = useRef<HTMLInputElement>(null);

    const addTag = useCallback((value: string) => {
        const trimmed = value.trim();
        if (!trimmed) return;
        setTags((prev) => (prev.includes(trimmed) ? prev : [...prev, trimmed]));
        setInput('');
    }, []);

    const removeTag = useCallback((index: number) => {
        setTags((prev) => prev.filter((_, i) => i !== index));
    }, []);

    const handleKeyDown = useCallback(
        (e: KeyboardEvent<HTMLInputElement>) => {
            if (e.key === 'Enter' || e.key === ',') {
                e.preventDefault();
                addTag(input);
            } else if (e.key === 'Backspace' && input === '' && tags.length > 0) {
                removeTag(tags.length - 1);
            }
        },
        [input, tags.length, addTag, removeTag],
    );

    const handleBlur = useCallback(() => {
        if (input.trim()) addTag(input);
    }, [input, addTag]);

    /** 送信直前に呼ぶ。input にあるテキストも含めて重複排除した最終配列を返す。 */
    const getFinalTags = useCallback((): string[] => {
        const final = input.trim() ? [...tags, input.trim()] : tags;
        return [...new Set(final)];
    }, [input, tags]);

    /** Dialog open 時の状態リセットに使う。引数省略で空配列にリセット。 */
    const reset = useCallback((next: string[] = []) => {
        setTags(next);
        setInput('');
    }, []);

    return {
        tags,
        input,
        inputRef,
        setInput,
        addTag,
        removeTag,
        handleKeyDown,
        handleBlur,
        getFinalTags,
        reset,
    };
}
