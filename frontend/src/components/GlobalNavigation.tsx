import { useEffect, useId, useRef, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Check, ChevronDown, FileText, Menu, Moon, Sun, Wrench, X } from 'lucide-react';
import { useDarkMode } from '@/hooks';
import {
    ACTIVE_CLASS,
    DESKTOP_CONTROL_CLASS,
    getCurrentLocation,
    INACTIVE_CLASS,
    isItemCurrent,
    NAV_GROUPS,
    type NavGroup,
    type RouteLocation,
} from '@/components/global-navigation-config';

interface DesktopCategoryMenuProps {
    group: NavGroup;
    pathname: string;
    open: boolean;
    onToggle: () => void;
    onNavigate: () => void;
}

function DesktopCategoryMenu({
    group,
    pathname,
    open,
    onToggle,
    onNavigate,
}: DesktopCategoryMenuProps) {
    const menuId = useId();
    const active = group.items.some((item) => isItemCurrent(item, pathname));

    return (
        <div className="relative">
            <button
                type="button"
                aria-label={`${group.label}メニュー`}
                aria-expanded={open}
                aria-controls={menuId}
                onClick={onToggle}
                className={`${DESKTOP_CONTROL_CLASS} ${active ? ACTIVE_CLASS : INACTIVE_CLASS}`}
            >
                <group.icon className="h-4 w-4" aria-hidden="true" />
                {group.label}
                <ChevronDown
                    className={`h-4 w-4 transition-transform ${open ? 'rotate-180' : ''}`}
                    aria-hidden="true"
                />
            </button>
            {open && (
                <div
                    id={menuId}
                    className="absolute left-0 top-full z-global-navigation mt-2 w-56 rounded-xl border border-gray-200 bg-white p-2 shadow-xl dark:border-gray-700 dark:bg-gray-800"
                >
                    {group.items.map((item) => {
                        const current = isItemCurrent(item, pathname);
                        return (
                            <Link
                                key={item.to}
                                to={item.to}
                                aria-label={item.ariaLabel}
                                aria-current={current ? 'page' : undefined}
                                onClick={onNavigate}
                                className={`flex min-h-11 items-center gap-3 rounded-lg px-3 text-sm font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 ${
                                    current ? ACTIVE_CLASS : INACTIVE_CLASS
                                }`}
                            >
                                <item.icon className="h-4 w-4" aria-hidden="true" />
                                {item.label}
                                {current && (
                                    <Check className="ml-auto h-4 w-4" aria-hidden="true" />
                                )}
                            </Link>
                        );
                    })}
                </div>
            )}
        </div>
    );
}

interface MobileDrawerProps {
    pathname: string;
    currentLocation: RouteLocation;
    onClose: () => void;
}

function MobileDrawer({ pathname, currentLocation, onClose }: MobileDrawerProps) {
    const drawerRef = useRef<HTMLElement>(null);
    const closeButtonRef = useRef<HTMLButtonElement>(null);

    useEffect(() => {
        closeButtonRef.current?.focus();
        const handleTab = (event: KeyboardEvent) => {
            if (event.key !== 'Tab' || !drawerRef.current?.contains(document.activeElement)) {
                return;
            }
            const focusable = Array.from(
                drawerRef.current.querySelectorAll<HTMLElement>('a[href], button:not([disabled])'),
            );
            if (focusable.length === 0) return;
            const first = focusable[0];
            const last = focusable[focusable.length - 1];
            if (event.shiftKey && document.activeElement === first) {
                event.preventDefault();
                last.focus();
            } else if (!event.shiftKey && document.activeElement === last) {
                event.preventDefault();
                first.focus();
            }
        };
        document.addEventListener('keydown', handleTab);
        return () => document.removeEventListener('keydown', handleTab);
    }, []);

    return (
        <div className="fixed inset-0 z-dialog lg:hidden">
            <button
                type="button"
                tabIndex={-1}
                aria-hidden="true"
                className="absolute inset-0 bg-black/55"
                onClick={onClose}
            />
            <nav
                id="mobile-global-navigation"
                ref={drawerRef}
                aria-label="モバイルナビゲーション"
                className="absolute inset-y-0 right-0 flex w-[min(22rem,88vw)] animate-slide-in-right flex-col overflow-y-auto border-l border-gray-200 bg-white shadow-2xl dark:border-gray-700 dark:bg-gray-900"
            >
                <div className="flex min-h-16 items-center gap-3 border-b border-gray-200 px-4 dark:border-gray-700">
                    <div className="min-w-0 flex-1">
                        <p className="text-xs font-medium text-primary-600 dark:text-primary-300">
                            {currentLocation.category}
                        </p>
                        <p className="truncate text-sm font-semibold text-gray-900 dark:text-gray-100">
                            {currentLocation.screen}
                        </p>
                    </div>
                    <button
                        ref={closeButtonRef}
                        type="button"
                        aria-label="メニューを閉じる"
                        onClick={onClose}
                        className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-gray-600 transition-colors hover:bg-gray-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 dark:text-gray-300 dark:hover:bg-gray-800"
                    >
                        <X className="h-5 w-5" aria-hidden="true" />
                    </button>
                </div>

                <div className="flex-1 p-3">
                    {NAV_GROUPS.map((group) => (
                        <section key={group.label} className="mb-3">
                            <h2 className="px-3 py-2 text-xs font-semibold text-gray-500 dark:text-gray-400">
                                {group.label}
                            </h2>
                            {group.items.map((item) => {
                                const current = isItemCurrent(item, pathname);
                                return (
                                    <Link
                                        key={item.to}
                                        to={item.to}
                                        aria-label={item.ariaLabel}
                                        aria-current={current ? 'page' : undefined}
                                        onClick={onClose}
                                        className={`flex min-h-11 items-center gap-3 rounded-lg px-3 text-sm font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 ${
                                            current ? ACTIVE_CLASS : INACTIVE_CLASS
                                        }`}
                                    >
                                        <item.icon className="h-4 w-4" aria-hidden="true" />
                                        {item.label}
                                        {current && (
                                            <Check className="ml-auto h-4 w-4" aria-hidden="true" />
                                        )}
                                    </Link>
                                );
                            })}
                        </section>
                    ))}
                </div>

                <div className="border-t border-gray-200 p-3 dark:border-gray-700">
                    <a
                        href="/site/index.html"
                        target="_blank"
                        rel="noopener noreferrer"
                        className={`${INACTIVE_CLASS} flex min-h-11 items-center gap-3 rounded-lg px-3 text-sm font-medium focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500`}
                    >
                        <Wrench className="h-4 w-4" aria-hidden="true" />
                        設計書
                    </a>
                </div>
            </nav>
        </div>
    );
}

export function GlobalNavigation() {
    const location = useLocation();
    const { isDark, toggle: toggleDark } = useDarkMode();
    const desktopNavRef = useRef<HTMLElement>(null);
    const mobileMenuButtonRef = useRef<HTMLButtonElement>(null);
    const [openCategory, setOpenCategory] = useState<string | null>(null);
    const [drawerOpen, setDrawerOpen] = useState(false);
    const currentLocation = getCurrentLocation(location.pathname);

    const closeDrawer = (restoreFocus = false) => {
        setDrawerOpen(false);
        if (restoreFocus) requestAnimationFrame(() => mobileMenuButtonRef.current?.focus());
    };

    useEffect(() => {
        if (!openCategory) return;
        const handlePointerDown = (event: PointerEvent) => {
            if (!desktopNavRef.current?.contains(event.target as Node)) setOpenCategory(null);
        };
        document.addEventListener('pointerdown', handlePointerDown);
        return () => document.removeEventListener('pointerdown', handlePointerDown);
    }, [openCategory]);

    useEffect(() => {
        const handleEscape = (event: KeyboardEvent) => {
            if (event.key !== 'Escape') return;
            if (drawerOpen) closeDrawer(true);
            setOpenCategory(null);
        };
        document.addEventListener('keydown', handleEscape);
        return () => document.removeEventListener('keydown', handleEscape);
    }, [drawerOpen]);

    useEffect(() => {
        if (!drawerOpen) return;
        const previousOverflow = document.body.style.overflow;
        document.body.style.overflow = 'hidden';
        return () => {
            document.body.style.overflow = previousOverflow;
        };
    }, [drawerOpen]);

    return (
        <header className="sticky top-0 z-global-navigation border-b border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900">
            <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
                <div className="hidden min-h-16 items-center gap-6 lg:flex">
                    <div className="flex shrink-0 items-center gap-2">
                        <span className="rounded-lg bg-primary-600 p-1.5">
                            <FileText className="h-6 w-6 text-white" aria-hidden="true" />
                        </span>
                        <span className="bg-gradient-to-r from-primary-500 to-primary-700 bg-clip-text text-xl font-bold text-transparent">
                            Pic2PDF Viewer
                        </span>
                    </div>

                    <nav
                        ref={desktopNavRef}
                        aria-label="グローバルナビゲーション"
                        className="flex min-w-0 flex-1 items-center gap-1"
                    >
                        {NAV_GROUPS.map((group) => {
                            if (group.desktopMode === 'menu') {
                                return (
                                    <DesktopCategoryMenu
                                        key={group.label}
                                        group={group}
                                        pathname={location.pathname}
                                        open={openCategory === group.label}
                                        onToggle={() =>
                                            setOpenCategory((current) =>
                                                current === group.label ? null : group.label,
                                            )
                                        }
                                        onNavigate={() => setOpenCategory(null)}
                                    />
                                );
                            }

                            const item = group.items[0];
                            const categoryActive = currentLocation.category === group.label;
                            return (
                                <Link
                                    key={group.label}
                                    to={item.to}
                                    aria-label={item.ariaLabel ?? item.label}
                                    aria-current={
                                        isItemCurrent(item, location.pathname) ? 'page' : undefined
                                    }
                                    className={`${DESKTOP_CONTROL_CLASS} ${categoryActive ? ACTIVE_CLASS : INACTIVE_CLASS}`}
                                >
                                    <group.icon className="h-4 w-4" aria-hidden="true" />
                                    {group.label === 'Kindle' ? item.label : group.label}
                                </Link>
                            );
                        })}
                    </nav>

                    <div className="flex shrink-0 items-center gap-1">
                        <a
                            href="/site/index.html"
                            target="_blank"
                            rel="noopener noreferrer"
                            aria-label="設計書を別タブで開く"
                            className="inline-flex h-11 w-11 items-center justify-center rounded-lg text-gray-600 transition-colors hover:bg-gray-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 dark:text-gray-300 dark:hover:bg-gray-800"
                        >
                            <Wrench className="h-5 w-5" aria-hidden="true" />
                        </a>
                        <button
                            type="button"
                            onClick={toggleDark}
                            aria-label={
                                isDark ? 'ライトモードに切り替え' : 'ダークモードに切り替え'
                            }
                            className="inline-flex h-11 w-11 items-center justify-center rounded-lg text-gray-600 transition-colors hover:bg-gray-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 dark:text-gray-300 dark:hover:bg-gray-800"
                        >
                            {isDark ? (
                                <Sun className="h-5 w-5" aria-hidden="true" />
                            ) : (
                                <Moon className="h-5 w-5" aria-hidden="true" />
                            )}
                        </button>
                    </div>
                </div>

                <div
                    className="hidden min-h-10 items-center gap-2 border-t border-gray-100 text-sm lg:flex dark:border-gray-800"
                    aria-label="現在地"
                >
                    <span className="font-medium text-primary-600 dark:text-primary-300">
                        {currentLocation.category}
                    </span>
                    <span className="text-gray-400 dark:text-gray-500" aria-hidden="true">
                        /
                    </span>
                    <span className="font-semibold text-gray-800 dark:text-gray-100">
                        {currentLocation.screen}
                    </span>
                </div>

                <div className="flex min-h-16 items-center gap-3 lg:hidden">
                    <div className="flex min-w-0 items-center gap-2">
                        <span className="shrink-0 rounded-lg bg-primary-600 p-1.5">
                            <FileText className="h-6 w-6 text-white" aria-hidden="true" />
                        </span>
                        <span className="truncate bg-gradient-to-r from-primary-500 to-primary-700 bg-clip-text text-sm font-bold text-transparent sm:text-base">
                            Pic2PDF Viewer
                        </span>
                    </div>
                    <div className="ml-auto min-w-0 text-right" aria-label="現在地">
                        <p className="truncate text-xs font-medium text-primary-600 dark:text-primary-300">
                            {currentLocation.category}
                        </p>
                        <p className="truncate text-sm font-semibold text-gray-800 dark:text-gray-100">
                            {currentLocation.screen}
                        </p>
                    </div>
                    <button
                        ref={mobileMenuButtonRef}
                        type="button"
                        aria-label="メニューを開く"
                        aria-expanded={drawerOpen}
                        aria-controls="mobile-global-navigation"
                        onClick={() => setDrawerOpen(true)}
                        className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-gray-700 transition-colors hover:bg-gray-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 dark:text-gray-200 dark:hover:bg-gray-800"
                    >
                        <Menu className="h-5 w-5" aria-hidden="true" />
                    </button>
                </div>
            </div>

            {drawerOpen && (
                <MobileDrawer
                    pathname={location.pathname}
                    currentLocation={currentLocation}
                    onClose={() => closeDrawer(true)}
                />
            )}
        </header>
    );
}
