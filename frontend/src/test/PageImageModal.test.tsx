import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import PageImageModal from '@/components/novel_db/PageImageModal';

describe('PageImageModal', () => {
    it('背景buttonと閉じるbuttonのどちらでも閉じられる', () => {
        const onClose = vi.fn();
        render(
            <PageImageModal
                book="book-a"
                pageNo={2}
                maxPage={3}
                onClose={onClose}
                onPrev={() => {}}
                onNext={() => {}}
            />,
        );

        expect(screen.getByRole('dialog', { name: 'book-a ページ 2' })).toBeInTheDocument();
        fireEvent.click(screen.getByRole('button', { name: '背景を選択して閉じる' }));
        fireEvent.click(screen.getByRole('button', { name: '閉じる' }));
        expect(onClose).toHaveBeenCalledTimes(2);
    });
});
