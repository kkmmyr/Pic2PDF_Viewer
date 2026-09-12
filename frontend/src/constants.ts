export const STORAGE_KEYS = {
    GENERATOR_JOB: 'generator_active_job',
    LIBRARY_SORT: 'librarySortOrder',
    DARK_MODE: 'darkMode',
    FAVORITES_PREFIX: 'favorites_',
    SERIES_PINS_PREFIX: 'pins_series_',
    AUTHOR_PINS_PREFIX: 'pins_author_',
} as const;

export const API_CONFIG = {
    TIMEOUT_MS: 30_000,
    POLL_INTERVAL_MS: 2000,
    JOB_POLL_INTERVAL_MS: 1500,
} as const;

export const UI_CONFIG = {
    SEARCH_DEBOUNCE_MS: 300,
    PRELOAD_MARGIN: '200px',
    READER_WHEEL_THRESHOLD_PX: 40,
    READER_WHEEL_GESTURE_END_MS: 180,
    READER_WHEEL_LINE_PX: 16,
} as const;

export const NOVEL_DB_CONFIG = {
    SEARCH_DEBOUNCE_MS: 300,
    SEARCH_PAGE_SIZE: 20,
    REBUILD_POLL_INTERVAL_MS: 5000,
    QUESTION_MAX_LENGTH: 500,
} as const;
