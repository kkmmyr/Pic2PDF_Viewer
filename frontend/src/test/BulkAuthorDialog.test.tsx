import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { BulkAuthorDialog } from '@/components/library/BulkAuthorDialog';

describe('BulkAuthorDialog', () => {
    it('既存作者は未選択で開始し、明示的に選択するまで適用しない', () => {
        const onApply = vi.fn().mockResolvedValue(undefined);

        render(
            <BulkAuthorDialog
                open
                targetCount={2}
                allAuthors={['先頭の作者', '次の作者']}
                onClose={() => {}}
                onApply={onApply}
            />,
        );

        expect(screen.getByRole('textbox')).toHaveValue('');

        fireEvent.click(screen.getByRole('button', { name: '一括適用' }));

        expect(screen.getByText('既存の作者を選択してください。')).toBeInTheDocument();
        expect(onApply).not.toHaveBeenCalled();
    });
});
