import { type InputHTMLAttributes, type Ref } from 'react';
import { cn } from '@/lib/utils';

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
    ref?: Ref<HTMLInputElement>;
}

export function Input({ ref, className, type, ...props }: InputProps) {
    return (
        <input
            type={type}
            ref={ref}
            className={cn(
                'flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs',
                'transition-colors placeholder:text-muted-foreground',
                'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring',
                'disabled:cursor-not-allowed disabled:opacity-50',
                'dark:bg-gray-800 dark:border-gray-600 dark:text-gray-100 dark:placeholder:text-gray-500',
                className,
            )}
            {...props}
        />
    );
}
