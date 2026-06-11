/* eslint-disable react-refresh/only-export-components */
import * as DropdownMenuPrimitive from '@radix-ui/react-dropdown-menu';
import { Check, ChevronRight, Circle } from 'lucide-react';
import { type ComponentPropsWithoutRef, type HTMLAttributes, type Ref } from 'react';
import { cn } from '@/lib/utils';

export const DropdownMenu = DropdownMenuPrimitive.Root;
export const DropdownMenuTrigger = DropdownMenuPrimitive.Trigger;
export const DropdownMenuGroup = DropdownMenuPrimitive.Group;
export const DropdownMenuPortal = DropdownMenuPrimitive.Portal;
export const DropdownMenuSub = DropdownMenuPrimitive.Sub;
export const DropdownMenuRadioGroup = DropdownMenuPrimitive.RadioGroup;

interface DropdownMenuSubTriggerProps extends ComponentPropsWithoutRef<
    typeof DropdownMenuPrimitive.SubTrigger
> {
    ref?: Ref<HTMLDivElement>;
    inset?: boolean;
}

export function DropdownMenuSubTrigger({
    ref,
    className,
    inset,
    children,
    ...props
}: DropdownMenuSubTriggerProps) {
    return (
        <DropdownMenuPrimitive.SubTrigger
            ref={ref}
            className={cn(
                'flex cursor-default select-none items-center gap-2 rounded-sm px-2 py-1.5 text-sm outline-none',
                'focus:bg-accent data-[state=open]:bg-accent',
                inset && 'pl-8',
                className,
            )}
            {...props}
        >
            {children}
            <ChevronRight className="ml-auto h-4 w-4" />
        </DropdownMenuPrimitive.SubTrigger>
    );
}

interface DropdownMenuSubContentProps extends ComponentPropsWithoutRef<
    typeof DropdownMenuPrimitive.SubContent
> {
    ref?: Ref<HTMLDivElement>;
}

export function DropdownMenuSubContent({ ref, className, ...props }: DropdownMenuSubContentProps) {
    return (
        <DropdownMenuPrimitive.SubContent
            ref={ref}
            className={cn(
                'z-50 min-w-32 overflow-hidden rounded-md border',
                'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700',
                'p-1 text-gray-900 dark:text-gray-100 shadow-lg',
                'data-[state=open]:animate-in data-[state=closed]:animate-out',
                'data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0',
                'data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95',
                'data-[side=bottom]:slide-in-from-top-2 data-[side=left]:slide-in-from-right-2',
                'data-[side=right]:slide-in-from-left-2 data-[side=top]:slide-in-from-bottom-2',
                className,
            )}
            {...props}
        />
    );
}

interface DropdownMenuContentProps extends ComponentPropsWithoutRef<
    typeof DropdownMenuPrimitive.Content
> {
    ref?: Ref<HTMLDivElement>;
}

export function DropdownMenuContent({
    ref,
    className,
    sideOffset = 4,
    ...props
}: DropdownMenuContentProps) {
    return (
        <DropdownMenuPrimitive.Portal>
            <DropdownMenuPrimitive.Content
                ref={ref}
                sideOffset={sideOffset}
                className={cn(
                    'z-50 min-w-32 overflow-hidden rounded-md border',
                    'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700',
                    'p-1 text-gray-900 dark:text-gray-100 shadow-md',
                    'data-[state=open]:animate-in data-[state=closed]:animate-out',
                    'data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0',
                    'data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95',
                    'data-[side=bottom]:slide-in-from-top-2 data-[side=left]:slide-in-from-right-2',
                    'data-[side=right]:slide-in-from-left-2 data-[side=top]:slide-in-from-bottom-2',
                    className,
                )}
                {...props}
            />
        </DropdownMenuPrimitive.Portal>
    );
}

interface DropdownMenuItemProps extends ComponentPropsWithoutRef<
    typeof DropdownMenuPrimitive.Item
> {
    ref?: Ref<HTMLDivElement>;
    inset?: boolean;
}

export function DropdownMenuItem({ ref, className, inset, ...props }: DropdownMenuItemProps) {
    return (
        <DropdownMenuPrimitive.Item
            ref={ref}
            className={cn(
                'relative flex cursor-default select-none items-center gap-2 rounded-sm px-2 py-1.5 text-sm outline-none transition-colors',
                'focus:bg-gray-100 dark:focus:bg-gray-700 focus:text-gray-900 dark:focus:text-gray-100',
                'data-[disabled]:pointer-events-none data-[disabled]:opacity-50',
                inset && 'pl-8',
                className,
            )}
            {...props}
        />
    );
}

interface DropdownMenuCheckboxItemProps extends ComponentPropsWithoutRef<
    typeof DropdownMenuPrimitive.CheckboxItem
> {
    ref?: Ref<HTMLDivElement>;
}

export function DropdownMenuCheckboxItem({
    ref,
    className,
    children,
    checked,
    ...props
}: DropdownMenuCheckboxItemProps) {
    return (
        <DropdownMenuPrimitive.CheckboxItem
            ref={ref}
            className={cn(
                'relative flex cursor-default select-none items-center rounded-sm py-1.5 pl-8 pr-2 text-sm outline-none transition-colors',
                'focus:bg-gray-100 dark:focus:bg-gray-700',
                'data-[disabled]:pointer-events-none data-[disabled]:opacity-50',
                className,
            )}
            checked={checked}
            {...props}
        >
            <span className="absolute left-2 flex h-3.5 w-3.5 items-center justify-center">
                <DropdownMenuPrimitive.ItemIndicator>
                    <Check className="h-4 w-4" />
                </DropdownMenuPrimitive.ItemIndicator>
            </span>
            {children}
        </DropdownMenuPrimitive.CheckboxItem>
    );
}

interface DropdownMenuRadioItemProps extends ComponentPropsWithoutRef<
    typeof DropdownMenuPrimitive.RadioItem
> {
    ref?: Ref<HTMLDivElement>;
}

export function DropdownMenuRadioItem({
    ref,
    className,
    children,
    ...props
}: DropdownMenuRadioItemProps) {
    return (
        <DropdownMenuPrimitive.RadioItem
            ref={ref}
            className={cn(
                'relative flex cursor-default select-none items-center rounded-sm py-1.5 pl-8 pr-2 text-sm outline-none transition-colors',
                'focus:bg-gray-100 dark:focus:bg-gray-700',
                'data-[disabled]:pointer-events-none data-[disabled]:opacity-50',
                className,
            )}
            {...props}
        >
            <span className="absolute left-2 flex h-3.5 w-3.5 items-center justify-center">
                <DropdownMenuPrimitive.ItemIndicator>
                    <Circle className="h-2 w-2 fill-current" />
                </DropdownMenuPrimitive.ItemIndicator>
            </span>
            {children}
        </DropdownMenuPrimitive.RadioItem>
    );
}

interface DropdownMenuLabelProps extends ComponentPropsWithoutRef<
    typeof DropdownMenuPrimitive.Label
> {
    ref?: Ref<HTMLDivElement>;
    inset?: boolean;
}

export function DropdownMenuLabel({ ref, className, inset, ...props }: DropdownMenuLabelProps) {
    return (
        <DropdownMenuPrimitive.Label
            ref={ref}
            className={cn(
                'px-2 py-1.5 text-xs font-semibold text-gray-500 dark:text-gray-400',
                inset && 'pl-8',
                className,
            )}
            {...props}
        />
    );
}

interface DropdownMenuSeparatorProps extends ComponentPropsWithoutRef<
    typeof DropdownMenuPrimitive.Separator
> {
    ref?: Ref<HTMLDivElement>;
}

export function DropdownMenuSeparator({ ref, className, ...props }: DropdownMenuSeparatorProps) {
    return (
        <DropdownMenuPrimitive.Separator
            ref={ref}
            className={cn('-mx-1 my-1 h-px bg-gray-200 dark:bg-gray-700', className)}
            {...props}
        />
    );
}

export function DropdownMenuShortcut({ className, ...props }: HTMLAttributes<HTMLSpanElement>) {
    return (
        <span
            className={cn(
                'ml-auto text-xs tracking-widest text-gray-400 dark:text-gray-500',
                className,
            )}
            {...props}
        />
    );
}
