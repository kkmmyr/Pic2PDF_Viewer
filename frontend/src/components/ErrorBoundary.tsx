import { Component, type ReactNode, type ErrorInfo } from 'react';

interface Props {
    children: ReactNode;
}

interface State {
    hasError: boolean;
    error: Error | null;
}

/**
 * 子コンポーネントの未捕捉エラーをキャッチし、
 * アプリ全体のクラッシュを防ぐエラーバウンダリ。
 */
class ErrorBoundary extends Component<Props, State> {
    constructor(props: Props) {
        super(props);
        this.state = { hasError: false, error: null };
    }

    static getDerivedStateFromError(error: Error): State {
        return { hasError: true, error };
    }

    componentDidCatch(error: Error, info: ErrorInfo) {
        console.error('ErrorBoundary caught an error:', error, info);
    }

    render() {
        if (!this.state.hasError) {
            return this.props.children;
        }

        return (
            <div style={styles.container}>
                <div style={styles.card}>
                    <span style={styles.icon}>⚠️</span>
                    <h2 style={styles.heading}>エラーが発生しました</h2>
                    <p style={styles.message}>
                        {this.state.error?.message ?? '不明なエラーが発生しました。'}
                    </p>
                    <button style={styles.button} onClick={() => window.location.reload()}>
                        再読み込み
                    </button>
                </div>
            </div>
        );
    }
}

export default ErrorBoundary;

const styles: Record<string, React.CSSProperties> = {
    container: {
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        minHeight: '100vh',
        padding: '20px',
        backgroundColor: '#f9fafb',
    },
    card: {
        padding: '40px',
        border: '2px solid #ef4444',
        borderRadius: '12px',
        maxWidth: '520px',
        width: '100%',
        textAlign: 'center',
        backgroundColor: '#fff',
        boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
    },
    icon: { fontSize: '3rem', display: 'block', marginBottom: '12px' },
    heading: { color: '#dc2626', fontSize: '1.5rem', marginBottom: '12px' },
    message: { color: '#6b7280', marginBottom: '24px', wordBreak: 'break-word' },
    button: {
        backgroundColor: '#ef4444',
        color: '#fff',
        border: 'none',
        padding: '10px 28px',
        borderRadius: '8px',
        cursor: 'pointer',
        fontSize: '1rem',
    },
};
