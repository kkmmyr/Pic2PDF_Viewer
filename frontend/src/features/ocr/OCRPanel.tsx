import React, { useState, useEffect, useRef } from 'react';
import { Box, Button, Card, CardContent, Typography, Alert, CircularProgress, Chip, Stack } from '@mui/material';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import StopIcon from '@mui/icons-material/Stop';
import TerminalIcon from '@mui/icons-material/Terminal';
import axios from 'axios';

const API_BASE = 'http://localhost:8000/api';

export const OCRPanel: React.FC = () => {
    const [status, setStatus] = useState<string>('idle');
    const [logs, setLogs] = useState<string[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const logEndRef = useRef<HTMLDivElement>(null);
    const pollingRef = useRef<number | null>(null);

    const fetchStatus = async () => {
        try {
            const res = await axios.get(`${API_BASE}/ocr/status`);
            setStatus(res.data.status);
            setLogs(res.data.logs);

            // Auto scroll only if running or just finished
            // Simply auto-scroll to bottom for now
        } catch (err) {
            console.error(err);
            // setError('Failed to fetch status');
        }
    };

    useEffect(() => {
        // Initial fetch
        fetchStatus();

        // Start polling
        pollingRef.current = window.setInterval(fetchStatus, 1000);

        return () => {
            if (pollingRef.current) clearInterval(pollingRef.current);
        };
    }, []);

    useEffect(() => {
        // Auto scroll to bottom when logs change
        logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [logs]);

    const handleStart = async () => {
        setLoading(true);
        setError(null);
        try {
            await axios.post(`${API_BASE}/ocr/run`);
            // Status will update via polling
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Failed to start OCR');
        } finally {
            setLoading(false);
        }
    };

    const handleStop = async () => {
        setLoading(true);
        try {
            await axios.post(`${API_BASE}/ocr/stop`);
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Failed to stop OCR');
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
