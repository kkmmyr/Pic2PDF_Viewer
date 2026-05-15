import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import { LibraryViewModeSelector } from '../components/novel_db/LibraryViewModeSelector';

const defaultProps = {
    groupMode: 'series' as const,
    totalCount: 10,
    isSelecting: false,
    onChangeMode: vi.fn(),
    onToggleSelecting: vi.fn(),
};

describe('LibraryViewModeSelector', () => {
    it('件数を見出しに表示する', () => {
        const { getByText } = render(<LibraryViewModeSelector {...defaultProps} totalCount={42} />);
        expect(getByText('ライブラリ (42 冊)')).toBeInTheDocument();
    });

    it('3つのモードボタンが表示される', () => {
        const { getByText } = render(<LibraryViewModeSelector {...defaultProps} />);
        expect(getByText('フラット')).toBeInTheDocument();
        expect(getByText('作者別')).toBeInTheDocument();
        expect(getByText('シリーズ別')).toBeInTheDocument();
    });

    it('アクティブなモードのボタンに bg-primary-600 が付く', () => {
        const { getByText } = render(
            <LibraryViewModeSelector {...defaultProps} groupMode="author" />,
        );
        expect(getByText('作者別').className).toContain('bg-primary-600');
        expect(getByText('フラット').className).not.toContain('bg-primary-600');
    });

    it('モードボタンをクリックすると onChangeMode が呼ばれる', () => {
        const onChangeMode = vi.fn();
        const { getByText } = render(
            <LibraryViewModeSelector {...defaultProps} onChangeMode={onChangeMode} />,
        );
        fireEvent.click(getByText('フラット'));
        expect(onChangeMode).toHaveBeenCalledWith('flat');
    });

    it('選択中でない場合「選択」ボタンに Square アイコンが描画される', () => {
        const { getByText } = render(
            <LibraryViewModeSelector {...defaultProps} isSelecting={false} />,
        );
        expect(getByText('選択')).toBeInTheDocument();
    });

    it('選択中の場合「選択」ボタンに bg-primary-100 系クラスが付く', () => {
        const { getByText } = render(
            <LibraryViewModeSelector {...defaultProps} isSelecting={true} />,
        );
        expect(getByText('選択').closest('button')!.className).toContain('bg-primary-100');
    });

    it('「選択」ボタンをクリックすると onToggleSelecting が呼ばれる', () => {
        const onToggleSelecting = vi.fn();
        const { getByText } = render(
            <LibraryViewModeSelector {...defaultProps} onToggleSelecting={onToggleSelecting} />,
        );
        fireEvent.click(getByText('選択'));
        expect(onToggleSelecting).toHaveBeenCalledTimes(1);
    });
});
