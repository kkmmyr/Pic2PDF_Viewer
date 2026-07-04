import { Component, type ReactNode, type ErrorInfo } from 'react';
import { ErrorFallbackCard } from '@/components/ui/error-fallback-card';

interface Props {
    children: ReactNode;
}

interface State {
    hasError: boolean;
    error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
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
            <ErrorFallbackCard
                message={this.state.error?.message ?? '不明なエラーが発生しました。'}
                action={
                    <button
                        className="inline-block bg-red-500 text-white px-7 py-2.5 rounded-lg text-base hover:bg-red-600 transition-colors cursor-pointer"
                        onClick={() => window.location.reload()}
                    >
                        再読み込み
                    </button>
                }
            />
        );
    }
}
