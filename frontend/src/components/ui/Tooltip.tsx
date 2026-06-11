import * as TooltipPrimitive from '@radix-ui/react-tooltip';
import { type ComponentPropsWithoutRef, type ReactNode, type Ref } from 'react';
import { cn } from '../../lib/utils';

export const TooltipProvider = TooltipPrimitive.Provider;
export const TooltipRoot = TooltipPrimitive.Root;
export const TooltipTrigger = TooltipPrimitive.Trigger;

interface TooltipContentProps extends ComponentPropsWithoutRef<typeof TooltipPrimitive.Content> {
    ref?: Ref<HTMLDivElement>;
}

export function TooltipContent({
    ref,
    className,
    sideOffset = 4,
    ...props
}: TooltipContentProps) {
    return (
        <TooltipPrimitive.Portal>
            <TooltipPrimitive.Content
                ref={ref}
                sideOffset={sideOffset}
                className={cn(
                    'z-50 overflow-hidden rounded-md bg-gray-900 dark:bg-gray-100',
                    'px-3 py-1.5 text-xs text-white dark:text-gray-900',
                    'animate-in fade-in-0 zoom-in-95',
                    'data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95',
                    'data-[side=bottom]:slide-in-from-top-2 data-[side=left]:slide-in-from-right-2',
                    'data-[side=right]:slide-in-from-left-2 data-[side=top]:slide-in-from-bottom-2',
                    className,
                )}
                {...props}
            />
        </TooltipPrimitive.Portal>
    );
}

/** 便利ラッパー: `<Tooltip content="..."><button /></Tooltip>` で使える。 */
export function Tooltip({
    children,
    content,
    delayDuration = 400,
}: {
    children: ReactNode;
    content: ReactNode;
    delayDuration?: number;
}) {
    return (
        <TooltipProvider>
            <TooltipRoot delayDuration={delayDuration}>
                <TooltipTrigger asChild>{children}</TooltipTrigger>
                <TooltipContent>{content}</TooltipContent>
            </TooltipRoot>
        </TooltipProvider>
    );
}
