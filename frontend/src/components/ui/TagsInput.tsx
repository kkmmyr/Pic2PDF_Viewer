import React, { type KeyboardEvent, type RefObject } from 'react';
import { X } from 'lucide-react';

const CHIP_CLASS = 'bg-primary-100 dark:bg-primary-900/50 text-primary-800 dark:text-primary-200';
const REMOVE_CLASS = 'hover:text-primary-600 dark:hover:text-primary-100 transition-colors';

interface TagsInputProps {
    tags: string[];
    input: string;
    inputRef: RefObject<HTMLInputElement | null>;
    placeholder?: string;
    hintText?: string;
    onChange: (value: string) => void;
    onKeyDown: (e: KeyboardEvent<HTMLInputElement>) => void;
    onRemove: (index: number) => void;
    onBlur?: () => void;
}

export function TagsInput({
    tags,
    input,
    inputRef,
    placeholder = '入力（Enter で確定）',
    hintText,
    onChange,
    onKeyDown,
    onRemove,
    onBlur,
}: TagsInputProps) {
    return (
        <>
            <div
                className="min-h-[2.5rem] w-full flex flex-wrap gap-1.5 px-2.5 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 cursor-text"
                onClick={() => inputRef.current?.focus()}
            >
                {tags.map((tag, i) => (
                    <span
                        key={i}
                        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${CHIP_CLASS}`}
                    >
                        {tag}
                        <button
                            type="button"
                            onClick={(e) => { e.stopPropagation(); onRemove(i); }}
                            className={REMOVE_CLASS}
                        >
                            <X className="w-3 h-3" />
                        </button>
                    </span>
                ))}
                <input
                    ref={inputRef as React.RefObject<HTMLInputElement>}
                    type="text"
                    value={input}
                    onChange={(e) => onChange(e.target.value)}
                    onKeyDown={onKeyDown}
                    onBlur={onBlur}
                    placeholder={tags.length === 0 ? placeholder : ''}
                    className="flex-1 min-w-[8rem] text-sm bg-transparent outline-none text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500"
                />
            </div>
            {hintText && (
                <p className="mt-1.5 text-xs text-gray-400 dark:text-gray-500">{hintText}</p>
            )}
        </>
    );
}
