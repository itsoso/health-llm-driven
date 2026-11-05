import { freshConversationPrompt, selectHomeSuggestions } from '../homePrompts';

it.each([
  [0, '聊聊现在的状态'], [4, '聊聊现在的状态'],
  [5, '聊聊昨晚的睡眠'], [10, '聊聊昨晚的睡眠'],
  [11, '聊聊今天的饮食'], [13, '聊聊今天的饮食'],
  [14, '聊聊下午的状态'], [17, '聊聊下午的状态'],
  [18, '回顾今天的状态'], [23, '回顾今天的状态'],
])('uses a neutral prompt at local hour %s', (hour, reply) => {
  expect(freshConversationPrompt(Number(hour)).reply).toBe(reply);
});

it('keeps backend ranking and attribution after cleaning the display candidates', () => {
  const items = [
    { text: '  ', key: 'empty' },
    { text: '拍照记一餐', key: 'retired' },
    { text: ' 看看记录 ', key: 'first' },
    { text: '看看记录', key: 'duplicate' },
    { text: '下一件事', key: 'second' },
  ];
  expect(selectHomeSuggestions(items)).toEqual([
    { text: ' 看看记录 ', key: 'first' }, { text: '下一件事', key: 'second' },
  ]);
  expect(selectHomeSuggestions(items)[0]).toBe(items[2]);
  expect(items[2].text).toBe(' 看看记录 ');
});
