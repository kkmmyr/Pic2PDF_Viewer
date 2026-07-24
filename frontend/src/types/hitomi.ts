/**
 * hitomi.la 新着監視機能の型定義。
 * 詳細は docs/design/詳細設計/機能別/hitomi新着監視設計書.md §4 を参照。
 */

import type { components } from '@/types/api';

export type ArrivalItem = components['schemas']['HitomiArrivalItem'];
export type NewArrivalsResponse = components['schemas']['HitomiArrivalsResponse'];
export type ArrivalStatus = NewArrivalsResponse['status'];
export type RunStatus = NewArrivalsResponse['last_run_status'];
export type RunStats = components['schemas']['HitomiRunStats'];
export type RunNowResponse = components['schemas']['HitomiRunNowResponse'];
export type WatchlistEntry = components['schemas']['HitomiWatchlistEntry'];
export type WatchlistResponse = components['schemas']['HitomiWatchlistResponse'];
