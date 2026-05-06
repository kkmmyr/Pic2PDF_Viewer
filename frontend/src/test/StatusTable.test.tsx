import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { StatusTable } from '../components/generator/StatusTable';
import type { StatusItem } from '../types';

const item = (name: string, type: string, status: StatusItem['status']): StatusItem => ({
    name,
    type,
    status,
});

describe('StatusTable', () => {
    it('items 空で何もレンダーしない（null 返す）', () => {
        const { container } = render(<StatusTable items={[]} />);
        expect(container.firstChild).toBeNull();
    });

    it('テーブル見出しと各 item 行を描画する', () => {
        const items: StatusItem[] = [
            item('a.pdf', 'pdf', 'completed'),
            item('b', 'folder', 'in_progress'),
            item('c.zip', 'zip', 'not_started'),
        ];
        const { getByText } = render(<StatusTable items={items} />);

        expect(getByText('アイテム状況')).toBeInTheDocument();
        expect(getByText('a.pdf')).toBeInTheDocument();
        expect(getByText('b')).toBeInTheDocument();
        expect(getByText('c.zip')).toBeInTheDocument();
    });

    it('各 status の表示ラベルが正しい', () => {
        const items: StatusItem[] = [
            item('A', 'pdf', 'completed'),
            item('B', 'pdf', 'in_progress'),
            item('C', 'pdf', 'not_started'),
        ];
        const { getByText } = render(<StatusTable items={items} />);
        expect(getByText('完了')).toBeInTheDocument();
        expect(getByText('処理中')).toBeInTheDocument();
        expect(getByText('未着手')).toBeInTheDocument();
    });

    it('completed の badge が緑系', () => {
        const { getByText } = render(<StatusTable items={[item('A', 'pdf', 'completed')]} />);
        expect(getByText('完了').className).toContain('bg-green-100');
    });

    it('in_progress の badge が primary 系', () => {
        const { getByText } = render(<StatusTable items={[item('A', 'pdf', 'in_progress')]} />);
        expect(getByText('処理中').className).toContain('bg-primary-100');
    });

    it('not_started の badge が gray 系', () => {
        const { getByText } = render(<StatusTable items={[item('A', 'pdf', 'not_started')]} />);
        expect(getByText('未着手').className).toContain('bg-gray-100');
    });

    it('item の type も表示される（uppercase 表記）', () => {
        const { container } = render(<StatusTable items={[item('A', 'pdf', 'completed')]} />);
        // CSS の uppercase で表示されるが、textContent は元の小文字で残る
        expect(container.textContent).toMatch(/pdf/);
    });
});
