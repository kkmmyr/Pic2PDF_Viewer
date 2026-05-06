import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { JobProgress } from '../components/generator/JobProgress';
import type { GenerateJob } from '../types';

const buildJob = (overrides: Partial<GenerateJob>): GenerateJob => ({
    job_id: 'jid',
    status: 'pending',
    current_item: null,
    files: [],
    failed_items: [],
    message: '',
    error: null,
    ...overrides,
});

describe('JobProgress', () => {
    it('pending 状態で「ジョブを開始中...」', () => {
        const { getByText } = render(<JobProgress job={buildJob({ status: 'pending' })} />);
        expect(getByText('ジョブを開始中...')).toBeInTheDocument();
    });

    it('running + current_item で「処理中: {name}」', () => {
        const { getByText } = render(
            <JobProgress job={buildJob({ status: 'running', current_item: 'book.pdf' })} />,
        );
        expect(getByText('処理中: book.pdf')).toBeInTheDocument();
    });

    it('running で current_item=null なら「処理中...」', () => {
        const { getByText } = render(
            <JobProgress job={buildJob({ status: 'running', current_item: null })} />,
        );
        expect(getByText('処理中...')).toBeInTheDocument();
    });

    it('completed で「生成完了」+ 緑系背景', () => {
        const { getByText, container } = render(
            <JobProgress job={buildJob({ status: 'completed' })} />,
        );
        expect(getByText('生成完了')).toBeInTheDocument();
        expect((container.firstChild as HTMLElement).className).toContain('bg-green-50');
    });

    it('failed で「生成に失敗しました」+ 赤系背景', () => {
        const { getByText, container } = render(
            <JobProgress job={buildJob({ status: 'failed', error: 'boom' })} />,
        );
        expect(getByText('生成に失敗しました')).toBeInTheDocument();
        expect((container.firstChild as HTMLElement).className).toContain('bg-red-50');
    });

    it('pending / running は primary 系背景', () => {
        const { container } = render(<JobProgress job={buildJob({ status: 'running' })} />);
        expect((container.firstChild as HTMLElement).className).toContain('bg-primary-50');
    });

    it('running 中は進捗バー（pulse）が表示される', () => {
        const { container } = render(<JobProgress job={buildJob({ status: 'running' })} />);
        // h-1.5 + animate-pulse のバー
        expect(container.querySelector('.animate-pulse')).not.toBeNull();
    });

    it('completed では進捗バーが表示されない', () => {
        const { container } = render(<JobProgress job={buildJob({ status: 'completed' })} />);
        // running 限定の div.bg-primary-200 は無いはず
        expect(container.querySelector('.bg-primary-200')).toBeNull();
    });
});
