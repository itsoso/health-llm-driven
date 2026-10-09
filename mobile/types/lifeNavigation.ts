// Native editor shapes mirror the existing API defaults; wire compatibility is checked by the service.
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
