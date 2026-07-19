import { remoteDietRepository } from '../remoteDietRepository';
import * as diet from '../diet';

jest.mock('../diet', () => ({
  getDailyDiet: jest.fn(),
  getDietStats: jest.fn(),
  getFrequentFoods: jest.fn(),
  createDietRecord: jest.fn(),
  updateDietRecord: jest.fn(),
  deleteDietRecord: jest.fn(),
}));

describe('remote diet repository', () => {
  it('preserves the existing cloud transport contract', async () => {
    (diet.getDailyDiet as jest.Mock).mockResolvedValue({ meals: [] });

    await expect(remoteDietRepository.getDailyDiet('2026-07-19')).resolves.toEqual({ meals: [] });
    expect(diet.getDailyDiet).toHaveBeenCalledWith('2026-07-19');
  });
});
