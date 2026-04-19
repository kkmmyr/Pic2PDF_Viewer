export const STORAGE_KEYS = {
    GENERATOR_JOB: 'generator_active_job',
    LIBRARY_SORT: 'librarySortOrder',
} as const;

export const API_CONFIG = {
    TIMEOUT_MS: 30_000,
    POLL_INTERVAL_MS: 2000,
    JOB_POLL_INTERVAL_MS: 1500,
} as const;
