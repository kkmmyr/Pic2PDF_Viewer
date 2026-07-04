import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { WatcherStatusCard } from '@/components/generator/WatcherStatusCard';
import type { DoujinWatcherState, DoujinWatcherStatus } from '@/types';

const buildWatcher = (overrides: Partial<DoujinWatcherStatus> = {}): DoujinWatcherStatus => ({
    enabled: true,
    state: 'idle',
    interval_sec: 15,
    last_scan_at: null,
    pending_items: [],
    active_job_id: null,
    last_auto_job: null,
    retry_blocked: false,
    ...overrides,
});

const STATE_LABEL: Record<DoujinWatcherState, string> = {
    idle: '監視中（新着なし）',
    waiting_stable: 'コピー完了待ち',
    running: '取り込み実行中',
    input_missing: '入力フォルダに接続できません',
    disabled: '自動取り込み無効',
};

describe('WatcherStatusCard', () => {
    it('watcher が null の場合は何もレンダーしない', () => {
        const { container } = render(<WatcherStatusCard watcher={null} />);
        expect(container.firstChild).toBeNull();
    });

    it.each(Object.keys(STATE_LABEL) as DoujinWatcherState[])(
        '%s 状態のラベルが表示される',
        (state) => {
            const { getByText } = render(<WatcherStatusCard watcher={buildWatcher({ state })} />);
            expect(getByText(STATE_LABEL[state])).toBeInTheDocument();
        },
    );

    it('pending_items の zip / folder 行が表示される', () => {
        const watcher = buildWatcher({
            pending_items: [
                { name: 'sample.zip', kind: 'zip' },
                { name: 'sample_folder', kind: 'folder' },
            ],
        });
        const { getByText } = render(<WatcherStatusCard watcher={watcher} />);
        expect(getByText('sample.zip')).toBeInTheDocument();
        expect(getByText('sample_folder')).toBeInTheDocument();
    });

    it('retry_blocked=true で警告文が表示される', () => {
        const watcher = buildWatcher({ retry_blocked: true });
        const { getByText } = render(<WatcherStatusCard watcher={watcher} />);
        expect(
            getByText('前回失敗したアイテムが残っています。『今すぐスキャン』で再試行できます'),
        ).toBeInTheDocument();
    });

    it('retry_blocked=false かつ pending_items が空なら警告文は表示されない', () => {
        const watcher = buildWatcher({ retry_blocked: false, pending_items: [] });
        const { queryByText } = render(<WatcherStatusCard watcher={watcher} />);
        expect(
            queryByText('前回失敗したアイテムが残っています。『今すぐスキャン』で再試行できます'),
        ).not.toBeInTheDocument();
    });

    it('最終スキャン時刻が null の場合は — が表示される', () => {
        const watcher = buildWatcher({ last_scan_at: null });
        const { getByText } = render(<WatcherStatusCard watcher={watcher} />);
        expect(getByText(/最終スキャン: —/)).toBeInTheDocument();
    });
});
