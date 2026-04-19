/**
 * Backward-compat barrel. 请改用 '@/components/chat/cards'.
 * 这里只 re-export 旧的 3 个 view 保持既有 import 不断裂.
 */
export {
  VitalsCardView as VitalsCard,
  ScoreCardView as ScoreCard,
  RecordCardView as RecordCard,
} from './cards';
