import { api } from './api/client';
export type TrackId = 'main' | 'aux1' | 'aux2' | 'important' | 'misc';
export type Slot = 'morning' | 'afternoon' | 'evening' | 'flexible';
export interface LifeTask {
    id: string;
    date: string;
    role: 'main' | 'auxiliary' | 'other';
    track_id: TrackId;
    slot: Slot;
    title: string;
    criterion: string;
    estimated_minutes: number | null;
    actual_minutes: number | null;
    status: 'planned' | 'doing' | 'done' | 'skipped';
    result: string;
    root_cause: string;
    improvement: string;
}
export interface LifeTrack {
    id: TrackId;
    title: string;
    criterion: string;
    strategy_link: string;
    next_step: string;
}
export interface DayNote {
    valuable: string;
    beautiful: string;
    mistake: string;
    learning: string;
}
export interface LifeReview {
    summary: string;
    gap: string;
    learning: string;
    next_week: string;
}
export interface LifeArchive {
    id: string;
    created_at: string;
    title: string;
    body: string;
    source_revision: number;
}
export interface LifeWeek {
    tracks: LifeTrack[];
    tasks: LifeTask[];
    notes: Record<string, DayNote>;
    review: LifeReview;
    archives: LifeArchive[];
}
export interface LifeQuarter {
    review: string;
    strategy: string;
    decomposition: string;
    plan: string;
    risk: string;
}
export interface LifeOpportunity {
    id: string;
    category: 'macro' | 'industry' | 'people' | 'customer';
    insight: string;
    evidence: string;
    personal_fit: string;
    assumption: string;
    next_step: string;
    success_criteria: string;
    risk_limit: string;
    review_date: string | null;
    result: string;
    evidence_level: 'unknown' | 'hypothesis' | 'signal' | 'supported';
    fit: 'unknown' | 'low' | 'medium' | 'high';
}
export interface LifeFocus {
    phase: 'idle' | 'focus' | 'rest' | 'paused';
    focus_minutes: number;
    rest_minutes: number;
    rounds: number;
    current_round: number;
    deadline: string | null;
    remaining_seconds: number | null;
    paused_phase: 'focus' | 'rest' | null;
    task_id: string | null;
}
export interface LifeData {
    strategy: {
        vision: string;
        annual_goal: string;
        primary_question: string;
    };
    quarters: Record<string, LifeQuarter>;
    weeks: Record<string, LifeWeek>;
    opportunities: LifeOpportunity[];
    focus: LifeFocus;
}
export interface LifeWorkspace {
    schema_version: 'life_navigation.v1';
    revision: number;
    data: LifeData;
    updated_at: string | null;
}
export interface LifeVersion {
    revision: number;
    data: LifeData;
    updated_at: string;
}
export interface LifeBackup {
    schema_version: 'life_navigation.backup.v1';
    workspace: LifeWorkspace;
    history: LifeVersion[];
}
const config = (owner: number, signal?: AbortSignal) => ({ headers: { 'X-Reva-AI-Subject': String(owner) }, ...(signal ? { signal } : {}) });
export async function getLifeWorkspace(owner: number, signal?: AbortSignal): Promise<LifeWorkspace> { return (await api.get('/life-navigation/workspace', config(owner, signal))).data; }
export async function saveLifeWorkspace(owner: number, revision: number, data: LifeData): Promise<LifeWorkspace> { return (await api.put('/life-navigation/workspace', { expected_revision: revision, data }, config(owner))).data; }
export async function getLifeHistory(owner: number): Promise<LifeVersion[]> { return (await api.get('/life-navigation/history', config(owner))).data; }
export async function restoreLifeWorkspace(owner: number, revision: number, expectedRevision: number): Promise<LifeWorkspace> { return (await api.post(`/life-navigation/restore/${revision}`, { expected_revision: expectedRevision }, config(owner))).data; }
export async function getLifeBackup(owner: number): Promise<LifeBackup> { return (await api.get('/life-navigation/backup', config(owner))).data; }
export async function importLifeBackup(owner: number, revision: number, backup: LifeBackup): Promise<LifeWorkspace> { return (await api.post('/life-navigation/import', { expected_revision: revision, backup }, config(owner))).data; }
