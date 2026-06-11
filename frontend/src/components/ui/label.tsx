import * as LabelPrimitive from '@radix-ui/react-label';
import { type ComponentPropsWithoutRef, type Ref } from 'react';
import { cn } from '@/lib/utils';

interface LabelProps extends ComponentPropsWithoutRef<typeof LabelPrimitive.Root> {
    ref?: Ref<HTMLLabelElement>;
}

export function Label({ ref, className, ...props }: LabelProps) {
    return (
        <LabelPrimitive.Root
            ref={ref}
            data-slot="label"
            className={cn(
                'text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70',
                'text-gray-700 dark:text-gray-300',
                className,
            )}
            {...props}
        />
    );
}
