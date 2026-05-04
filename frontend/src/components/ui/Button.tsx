import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react';

export type ButtonVariant = 'primary' | 'secondary' | 'danger' | 'ghost';
export type ButtonSize = 'sm' | 'md' | 'lg';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
    variant?: ButtonVariant;
    size?: ButtonSize;
    children?: ReactNode;
}

const SIZE_CLASS: Record<ButtonSize, string> = {
    sm: 'px-2.5 py-1 text-xs gap-1',
    md: 'px-3 py-1.5 text-sm gap-1.5',
    lg: 'px-6 py-3 text-base gap-2',
};

const VARIANT_CLASS: Record<ButtonVariant, string> = {
    primary:
        'bg-primary-600 hover:bg-primary-700 text-white ' +
        'disabled:bg-primary-300 dark:disabled:bg-primary-900 disabled:hover:bg-primary-300',
    secondary:
        'bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 ' +
        'hover:bg-gray-200 dark:hover:bg-gray-700 disabled:opacity-50',
    danger:
        'bg-red-600 hover:bg-red-700 text-white disabled:opacity-50',
    ghost:
        'bg-transparent text-gray-700 dark:text-gray-300 ' +
        'hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-50',
};

const BASE_CLASS =
    'inline-flex items-center justify-center rounded-md font-medium ' +
    'transition-colors disabled:cursor-not-allowed';

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
    { variant = 'primary', size = 'md', className = '', children, type = 'button', ...rest },
    ref,
) {
    const classes = `${BASE_CLASS} ${SIZE_CLASS[size]} ${VARIANT_CLASS[variant]} ${className}`.trim();
    return (
        <button ref={ref} type={type} className={classes} {...rest}>
            {children}
        </button>
    );
});
