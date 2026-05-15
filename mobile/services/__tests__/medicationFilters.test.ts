import { filterMedicationRecordItems } from '../medicationFilters';

describe('filterMedicationRecordItems', () => {
  it('keeps only drug-like medication records and removes supplements', () => {
    const items = [
      { name: '维生素 C粉 (Life Extension Buffered Vitamin C)', category: null },
      { name: '甘氨酸镁 Magnesium Glycinate', category: 'supplement' },
      { name: '褪黑素 Melatonin', category: '保健品' },
      { name: '异丙托溴铵鼻喷雾剂', category: null },
      { name: '糠酸莫米松鼻喷雾剂', category: null },
      { name: '盐酸西替利嗪片', category: '非处方药' },
      { name: '兰美抒 盐酸特比萘芬乳膏', category: '药品' },
    ];

    expect(filterMedicationRecordItems(items).map(item => item.name)).toEqual([
      '异丙托溴铵鼻喷雾剂',
      '糠酸莫米松鼻喷雾剂',
      '盐酸西替利嗪片',
      '兰美抒 盐酸特比萘芬乳膏',
    ]);
  });
});
