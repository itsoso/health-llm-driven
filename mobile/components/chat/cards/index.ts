/**
 * 动态卡片系统 barrel exports
 */
export * from './types';
export * from './registry';
export { CardShell } from './CardShell';

// 单卡组件 (兜底直接 import)
export { VitalsCardView } from './VitalsCard';
export { SleepCardView } from './SleepCard';
export { WeightCardView } from './WeightCard';
export { SupplementCardView } from './SupplementCard';
export { WeatherCardView } from './WeatherCard';
export { BPCardView } from './BPCard';
export { ScoreCardView } from './ScoreCard';
export { RecordCardView } from './RecordCard';
export { MedicationDraftCardView } from './MedicationDraftCard';
export { SupplementDraftCardView } from './SupplementDraftCard';
export { DietCardView } from './DietCard';
export { RuntimeAgendaCardView } from './RuntimeAgendaCard';
export { HealthEvidenceCardView } from './HealthEvidenceCard';
