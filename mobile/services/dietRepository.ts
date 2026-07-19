import type {
  DailyDietSummary,
  DietRecord,
  DietRecordCreate,
  DietRecordUpdate,
  DietStats,
  FrequentFood,
} from './diet';

export interface DietRepository {
  getDailyDiet(date: string): Promise<DailyDietSummary>;
  getDietStats(days?: number): Promise<DietStats>;
  getFrequentFoods(limit?: number, days?: number): Promise<FrequentFood[]>;
  createDietRecord(record: DietRecordCreate): Promise<DietRecord>;
  updateDietRecord(id: number, patch: DietRecordUpdate): Promise<DietRecord>;
  deleteDietRecord(id: number): Promise<void>;
}
