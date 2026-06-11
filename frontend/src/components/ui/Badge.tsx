import { cva, type VariantProps } from 'class-variance-authority';
import { type HTMLAttributes } from 'react';
import { cn } from '@/lib/utils';

const badgeVariants = cva(
    'inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors',
    {
        variants: {
            variant: {
                default: 'border-transparent bg-primary-600 text-white',
                secondary:
                    'border-transparent bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300',
                destructive: 'border-transparent bg-red-600 text-white',
                outline: 'border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300',
                success:
                    'border-transparent bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400',
            },
        },
        defaultVariants: {
            variant: 'default',
        },
    },
);

interface BadgeProps extends HTMLAttributes<HTMLDivElement>, VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
    return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { badgeVariants };
