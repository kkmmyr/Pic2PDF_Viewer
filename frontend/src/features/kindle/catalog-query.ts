import type {
    KindleBookType,
    KindleCatalogFilters,
    KindleCaptureState,
    KindleOwnership,
} from '@/features/kindle/types';

export const DEFAULT_KINDLE_CATALOG_PAGE_SIZE = 25;
export const KINDLE_CATALOG_PAGE_SIZE_OPTIONS = [25, 50, 100] as const;

const BOOK_TYPES = ['comic', 'novel', 'other', 'unknown'] as const;
const OWNERSHIP_TYPES = [
    'purchased',
    'borrowed_active',
    'borrowed_ended',
    'returned',
    'unknown',
] as const;
const CAPTURE_STATES = ['not_captured', 'captured', 'multiple_links', 'capture_pending'] as const;

function parsePositiveInt(value: string | null, fallback: number): number {
    const parsed = Number(value);
    return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback;
}

function parseEnumParam<T extends string>(value: string | null, allowed: readonly T[]): T | '' {
    return value && allowed.includes(value as T) ? (value as T) : '';
}

export function parseKindleCatalogQuery(params: URLSearchParams): KindleCatalogFilters {
    const requestedPageSize = parsePositiveInt(
        params.get('page_size'),
        DEFAULT_KINDLE_CATALOG_PAGE_SIZE,
    );
    const pageSize = KINDLE_CATALOG_PAGE_SIZE_OPTIONS.includes(
        requestedPageSize as (typeof KINDLE_CATALOG_PAGE_SIZE_OPTIONS)[number],
    )
        ? requestedPageSize
        : DEFAULT_KINDLE_CATALOG_PAGE_SIZE;
    return {
        q: params.get('q') ?? '',
        bookType: parseEnumParam<Exclude<KindleBookType, ''>>(params.get('book_type'), BOOK_TYPES),
        ownership: parseEnumParam<Exclude<KindleOwnership, ''>>(
            params.get('ownership'),
            OWNERSHIP_TYPES,
        ),
        captureState: parseEnumParam<Exclude<KindleCaptureState, ''>>(
            params.get('capture_state'),
            CAPTURE_STATES,
        ),
        page: parsePositiveInt(params.get('page'), 1),
        pageSize,
    };
}

export function replaceKindleCatalogParam(
    current: URLSearchParams,
    key: string,
    value: string,
    resetPage = true,
): URLSearchParams {
    const next = new URLSearchParams(current);
    if (value) next.set(key, value);
    else next.delete(key);
    if (resetPage) next.delete('page');
    return next;
}

export function clearKindleCatalogFilters(current: URLSearchParams): URLSearchParams {
    const next = new URLSearchParams(current);
    for (const key of ['q', 'book_type', 'ownership', 'capture_state', 'page']) {
        next.delete(key);
    }
    return next;
}
