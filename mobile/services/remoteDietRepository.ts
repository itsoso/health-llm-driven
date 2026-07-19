import {
  createDietRecord,
  deleteDietRecord,
  getDailyDiet,
  getDietStats,
  getFrequentFoods,
  updateDietRecord,
} from './diet';
import type { DietRepository } from './dietRepository';

export const remoteDietRepository: DietRepository = {
  getDailyDiet,
  getDietStats,
  getFrequentFoods,
  createDietRecord,
  updateDietRecord,
  deleteDietRecord,
};
