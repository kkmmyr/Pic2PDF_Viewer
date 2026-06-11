import { cva, type VariantProps } from 'class-variance-authority';
import { type ButtonHTMLAttributes, type ReactNode, type Ref } from 'react';
import { cn } from '../../lib/utils';

const buttonVariants = cva(
    'inline-flex items-center justify-center rounded-md font-medium transition-colors disabled:cursor-not-allowed',
    {
        variants: {
            variant: {
                primary:
                    'bg-primary-600 hover:bg-primary-700 text-white ' +
                    'disabled:bg-primary-300 dark:disabled:bg-primary-900 disabled:hover:bg-primary-300',
                secondary:
                    'bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 ' +
                    'hover:bg-gray-200 dark:hover:bg-gray-700 disabled:opacity-50',
                danger: 'bg-red-600 hover:bg-red-700 text-white disabled:opacity-50',
                ghost:
                    'bg-transparent text-gray-700 dark:text-gray-300 ' +
                    'hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-50',
            },
            size: {
                sm: 'px-2.5 py-1 text-xs gap-1',
                md: 'px-3 py-1.5 text-sm gap-1.5',
                lg: 'px-6 py-3 text-base gap-2',
            },
            active: {
                true: '',
                false: '',
            },
        },
        compoundVariants: [
            {
                variant: 'secondary',
                active: true,
                class:
                    'bg-gray-700 dark:bg-gray-700 text-white dark:text-white ' +
                    'hover:bg-gray-800 dark:hover:bg-gray-800',
            },
        ],
        defaultVariants: {
            variant: 'primary',
            size: 'md',
            active: false,
        },
    },
);

interface ButtonProps
    extends ButtonHTMLAttributes<HTMLButtonElement>,
        VariantProps<typeof buttonVariants> {
    /** React 19: ref を通常 prop として受け取る（forwardRef 不要）。 */
    ref?: Ref<HTMLButtonElement>;
    /** トグル ON 状態（secondary variant 専用）。gray-700 ベースで強調表示。 */
    active?: boolean;
    children?: ReactNode;
}

export { buttonVariants };

export function Button({
    ref,
    variant = 'primary',
    size = 'md',
    active = false,
    className = '',
    children,
    type = 'button',
    ...rest
}: ButtonProps) {
    return (
        <button
            ref={ref}
            type={type}
            className={cn(buttonVariants({ variant, size, active }), className)}
            {...rest}
        >
            {children}
        </button>
    );
}
