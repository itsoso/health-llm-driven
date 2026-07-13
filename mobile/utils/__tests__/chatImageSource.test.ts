import { buildChatImageSource } from '../chatImageSource';

describe('buildChatImageSource', () => {
  it('adds bearer auth to every protected health image URL', () => {
    expect(buildChatImageSource(
      'https://health.example/api/v1/upload/files/chat/7/meal.jpg',
      'secret-token',
    )).toEqual({
      uri: 'https://health.example/api/v1/upload/files/chat/7/meal.jpg',
      headers: { Authorization: 'Bearer secret-token' },
    });
    expect(buildChatImageSource('file:///drafts/meal.jpg', 'secret-token')).toEqual({
      uri: 'file:///drafts/meal.jpg',
    });
    expect(buildChatImageSource(
      'https://health.example/api/v1/upload/files/diet/7/meal.jpg',
      'secret-token',
    )).toEqual({
      uri: 'https://health.example/api/v1/upload/files/diet/7/meal.jpg',
      headers: { Authorization: 'Bearer secret-token' },
    });
    expect(buildChatImageSource(
      'https://health.example/api/v1/upload/files/avatar/profile.jpg',
      'secret-token',
    )).toEqual({
      uri: 'https://health.example/api/v1/upload/files/avatar/profile.jpg',
    });
  });

  it('does not build an unauthenticated source for a protected chat image', () => {
    expect(buildChatImageSource(
      'https://health.example/api/v1/upload/files/chat/7/meal.jpg',
      null,
    )).toBeUndefined();
    expect(buildChatImageSource(
      'https://health.example/api/v1/upload/files/medical/7/lab.jpg',
      null,
    )).toBeUndefined();
  });
});
