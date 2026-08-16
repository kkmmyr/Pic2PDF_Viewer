import { API_CONFIG } from '@/config/api';
import { postSseStream } from '@/features/novel_db/sse-transport';
import type { DiscussionChecks } from '@/features/novel_db/types';
import type { components } from '@/types/api';

export type DiscussionGenerateRequest = components['schemas']['GenerateRequest'];
export type DiscussionStage = 'planning' | 'scripting';

export interface DiscussionSegmentEvent {
    id: string;
    title: string;
}

export interface DiscussionTurnEvent {
    speaker: 'A' | 'B';
    text: string;
    segment?: string;
}

export interface DiscussionDoneEvent {
    saved_path?: string;
    checks: DiscussionChecks | null;
}

export interface DiscussionStreamHandlers {
    onStatus: (stage: DiscussionStage) => void;
    onSegment: (event: DiscussionSegmentEvent) => void;
    onTurn: (event: DiscussionTurnEvent) => void;
    onDone: (event: DiscussionDoneEvent) => void;
    onError: (error: Error) => void;
}

interface DiscussionSsePayload {
    type?: string;
    stage?: string;
    id?: string;
    title?: string;
    speaker?: string;
    text?: string;
    segment?: string;
    saved_path?: string;
    checks?: DiscussionChecks;
    message?: string;
}

export async function streamDiscussion(
    body: DiscussionGenerateRequest,
    handlers: DiscussionStreamHandlers,
    signal?: AbortSignal,
): Promise<void> {
    const error = await postSseStream<DiscussionSsePayload>(
        `${API_CONFIG.BASE_URL}/api/novel/discussion/generate`,
        body,
        (event) => handleDiscussionEvent(event, handlers),
        signal,
    );
    if (error && error.message !== 'aborted') handlers.onError(error);
}

function handleDiscussionEvent(
    event: DiscussionSsePayload,
    handlers: DiscussionStreamHandlers,
): 'stop' | void {
    if (event.type === 'status' && (event.stage === 'planning' || event.stage === 'scripting')) {
        handlers.onStatus(event.stage);
    } else if (event.type === 'segment' && event.id && event.title !== undefined) {
        handlers.onSegment({ id: event.id, title: event.title });
    } else if (
        event.type === 'turn' &&
        (event.speaker === 'A' || event.speaker === 'B') &&
        event.text !== undefined
    ) {
        handlers.onTurn({ speaker: event.speaker, text: event.text, segment: event.segment });
    } else if (event.type === 'done') {
        handlers.onDone({ saved_path: event.saved_path, checks: event.checks ?? null });
        return 'stop';
    } else if (event.type === 'error' || event.message !== undefined) {
        handlers.onError(new Error(event.message ?? 'Unknown error'));
        return 'stop';
    }
}
