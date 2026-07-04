import { useQuery } from '@tanstack/react-query';
import generateApiClient from '@/config/generate_api_client';
import { API_ENDPOINTS } from '@/config/api';
import type { DoujinWatcherStatus } from '@/types';

/**
 * 同人誌フォルダ自動監視（バックエンド watcher）の状態を 5 秒間隔でポーリングする。
 * エラー時も throw せず `watcher: null` を返す（呼び出し側でのクラッシュを防ぐ）。
 */
export function useDoujinWatcher() {
    const { data, isError } = useQuery<DoujinWatcherStatus>({
        queryKey: ['doujinWatcher'],
        queryFn: () =>
            generateApiClient.get<unknown, DoujinWatcherStatus>(API_ENDPOINTS.GENERATE_WATCHER),
        refetchInterval: 5000,
        staleTime: 0,
        gcTime: 30_000,
        retry: false,
    });

    return { watcher: data ?? null, isError };
}
