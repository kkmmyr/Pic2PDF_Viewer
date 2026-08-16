import {
    BookOpen,
    BookText,
    Database,
    Library,
    MessageSquare,
    Settings,
    Share2,
    ShoppingBag,
    Sparkles,
    Wrench,
    type LucideIcon,
} from 'lucide-react';

export interface NavItem {
    to: string;
    label: string;
    ariaLabel?: string;
    icon: LucideIcon;
    activePrefixes?: readonly string[];
}

export interface NavGroup {
    label: string;
    icon: LucideIcon;
    desktopMode: 'menu' | 'link';
    items: readonly NavItem[];
}

export interface RouteLocation {
    category: string;
    screen: string;
}

export const NAV_GROUPS: readonly NavGroup[] = [
    {
        label: '同人誌',
        icon: Library,
        desktopMode: 'menu',
        items: [
            { to: '/doujin', icon: Library, label: 'ライブラリ', ariaLabel: '同人誌ライブラリ' },
            { to: '/doujin/generator', icon: Settings, label: '取り込み' },
            { to: '/doujin/hitomi', icon: Sparkles, label: '新着' },
        ],
    },
    {
        label: '漫画',
        icon: BookOpen,
        desktopMode: 'link',
        items: [{ to: '/comic', icon: Library, label: 'ライブラリ', ariaLabel: '漫画ライブラリ' }],
    },
    {
        label: '小説',
        icon: BookText,
        desktopMode: 'menu',
        items: [
            {
                to: '/novel/db',
                icon: Database,
                label: '書籍DB',
                activePrefixes: ['/novel/detail/', '/novel/reader/'],
            },
            { to: '/novel/discussion', icon: MessageSquare, label: '読書会' },
            { to: '/novel/graph', icon: Share2, label: '関係グラフ' },
            { to: '/novel/manage', icon: Wrench, label: '管理' },
        ],
    },
    {
        label: 'Kindle',
        icon: ShoppingBag,
        desktopMode: 'link',
        items: [{ to: '/kindle/catalog', icon: ShoppingBag, label: '購入書籍' }],
    },
];

export const DESKTOP_CONTROL_CLASS =
    'inline-flex min-h-11 items-center gap-2 rounded-lg px-3 text-sm font-medium whitespace-nowrap transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-gray-900';
export const ACTIVE_CLASS =
    'bg-primary-50 text-primary-700 dark:bg-primary-900/40 dark:text-primary-300';
export const INACTIVE_CLASS =
    'text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800';

export function isItemCurrent(item: NavItem, pathname: string): boolean {
    return (
        pathname === item.to ||
        item.activePrefixes?.some((prefix) => pathname.startsWith(prefix)) === true
    );
}

export function getCurrentLocation(pathname: string): RouteLocation {
    if (pathname === '/doujin/generator') return { category: '同人誌', screen: '取り込み' };
    if (pathname === '/doujin/hitomi') return { category: '同人誌', screen: '新着' };
    if (pathname === '/doujin') return { category: '同人誌', screen: 'ライブラリ' };
    if (pathname === '/comic') return { category: '漫画', screen: 'ライブラリ' };
    if (pathname.startsWith('/novel/detail/')) return { category: '小説', screen: '書籍詳細' };
    if (pathname.startsWith('/novel/reader/')) return { category: '小説', screen: '本文' };
    if (pathname === '/novel/discussion') return { category: '小説', screen: '読書会' };
    if (pathname === '/novel/graph') return { category: '小説', screen: '関係グラフ' };
    if (pathname === '/novel/manage') return { category: '小説', screen: '管理' };
    if (pathname.startsWith('/novel')) return { category: '小説', screen: '書籍DB' };
    if (pathname === '/kindle/links') return { category: 'Kindle', screen: '画像紐付け' };
    if (pathname === '/kindle/capture') return { category: 'Kindle', screen: 'キャプチャ' };
    if (pathname === '/kindle/imports') return { category: 'Kindle', screen: '取込・管理' };
    if (pathname.startsWith('/kindle')) return { category: 'Kindle', screen: '購入書籍' };
    return { category: 'Pic2PDF Viewer', screen: 'ホーム' };
}
