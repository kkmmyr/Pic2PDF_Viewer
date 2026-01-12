import React from 'react';
import { Box, Container } from '@mui/material';
import { OCRPanel } from '../features/ocr/OCRPanel';

const OCRPage: React.FC = () => {
    return (
        <Container maxWidth="lg" sx={{ py: 4, height: 'calc(100vh - 80px)' }}>
            <OCRPanel />
        </Container>
    );
};

export default OCRPage;
