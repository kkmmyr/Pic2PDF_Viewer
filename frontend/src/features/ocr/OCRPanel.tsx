import React, { useState, useEffect, useRef } from 'react';
import { Box, Button, Card, CardContent, Typography, Alert, CircularProgress, Chip, Stack } from '@mui/material';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import StopIcon from '@mui/icons-material/Stop';
import TerminalIcon from '@mui/icons-material/Terminal';
import { useOcrStatus } from '../../hooks/useOcrStatus';

export const OCRPanel: React.FC = () => {
    const { status, logs, startOcr, stopOcr } = useOcrStatus();
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const logEndRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        // Auto scroll to bottom when logs change
        logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [logs]);

    const handleStart = async () => {
        setLoading(true);
        setError(null);
        try {
            await startOcr();
        } catch (err: any) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    const handleStop = async () => {
        setLoading(true);
        try {
            await stopOcr();
        } catch (err: any) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    const isRunning = status === 'running';

    return (
        <Card sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
            <CardContent sx={{ flexShrink: 0 }}>
                <Stack direction="row" alignItems="center" spacing={2} mb={2}>
                    <Typography variant="h5" component="div">
                        Novel OCR Execution
                    </Typography>
                    <Chip
                        label={status.toUpperCase()}
                        color={status === 'running' ? 'primary' : status === 'idle' ? 'default' : 'error'}
                        variant={status === 'running' ? 'filled' : 'outlined'}
                    />
                </Stack>

                <Stack direction="row" spacing={2} mb={2}>
                    <Button
                        variant="contained"
                        color="primary"
                        startIcon={loading ? <CircularProgress size={20} color="inherit" /> : <PlayArrowIcon />}
                        onClick={handleStart}
                        disabled={isRunning || loading}
                    >
                        Start OCR
                    </Button>
                    <Button
                        variant="contained"
                        color="error"
                        startIcon={<StopIcon />}
                        onClick={handleStop}
                        disabled={!isRunning || loading}
                    >
                        Stop OCR
                    </Button>
                </Stack>

                {error && (
                    <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>
                )}
            </CardContent>

            <Box sx={{
                flexGrow: 1,
                bgcolor: '#1e1e1e',
                color: '#d4d4d4',
                p: 2,
                overflowY: 'auto',
                fontFamily: 'Consolas, Monaco, "Andale Mono", "Ubuntu Mono", monospace',
                fontSize: '0.9rem',
                mx: 2,
                mb: 2,
                borderRadius: 1,
                border: '1px solid #333'
            }}>
                <Stack direction="row" alignItems="center" spacing={1} mb={1} sx={{ color: '#888', borderBottom: '1px solid #333', pb: 1 }}>
                    <TerminalIcon fontSize="small" />
                    <Typography variant="caption">Console Output (batch_ocr.py)</Typography>
                </Stack>

                {logs.length === 0 ? (
                    <Typography color="gray" fontStyle="italic">No logs available.</Typography>
                ) : (
                    logs.map((line, index) => (
                        <div key={index} style={{ whiteSpace: 'pre-wrap', lineHeight: '1.4' }}>
                            {line}
                        </div>
                    ))
                )}
                <div ref={logEndRef} />
            </Box>
        </Card>
    );
};
