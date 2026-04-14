import React from 'react';
import { OCRPanel } from '../features/ocr/OCRPanel';

const OCRPage: React.FC = () => {
    return (
        <div className="max-w-5xl mx-auto px-4 py-6 h-[calc(100vh-80px)] flex flex-col">
            <OCRPanel />
        </div>
    );
};

export default OCRPage;
