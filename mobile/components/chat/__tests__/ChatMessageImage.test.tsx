import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';
import { Image } from 'expo-image';
import { ChatMessageImage } from '../ChatMessageImage';

jest.mock('../../../services/api', () => ({ BASE_URL: 'https://health.example/api/v1' }));

describe('chat thumbnail source boundaries', () => {
  it.each([
    'file:///draft.jpg',
    'data:image/png;base64,example',
    'https://external.example/api/v1/upload/files/chat/7/photo.jpg',
    'https://health.example/api/v1/upload/files/medical/7/photo.jpg',
    'https://health.example/api/v1/upload/files/avatar/photo.jpg',
  ])('keeps unsupported source unchanged: %s', uri => {
    const source = { uri };
    const view = render(<ChatMessageImage source={source} style={{ width: 160, height: 120 }} />);
    expect(view.UNSAFE_getByType(Image).props.source).toBe(source);
  });

  it('retains capability and auth, replaces an existing variant, and retries a new source', () => {
    const source = {
      uri: 'https://health.example/api/v1/upload/files/diet/7/photo.jpg?signature=abc&expires=123&variant=original',
      headers: { Authorization: 'Bearer secret' },
    };
    const view = render(<ChatMessageImage source={source} style={{ width: 160 }} />);
    expect(view.UNSAFE_getByType(Image).props.source).toEqual({
      ...source, uri: source.uri.replace('variant=original', 'variant=preview'),
    });
    expect(source.uri).toContain('variant=original');
    fireEvent(view.UNSAFE_getByType(Image), 'error', { error: 'unavailable' });
    expect(view.UNSAFE_getByType(Image).props.source).toBe(source);
    const next = { ...source, uri: source.uri.replace('photo.jpg', 'next.jpg') };
    view.rerender(<ChatMessageImage source={next} style={{ width: 160 }} />);
    expect(view.UNSAFE_getByType(Image).props.source.uri).toBe(next.uri.replace('variant=original', 'variant=preview'));
    expect(view.UNSAFE_getByType(Image).props.recyclingKey).toBe(next.uri);
  });

  it('shows an explicit retry state after both preview and original fail', () => {
    const source = {
      uri: 'https://health.example/api/v1/upload/files/chat/7/photo.jpg?signature=abc&expires=123',
      headers: { Authorization: 'Bearer secret' },
    };
    const view = render(<ChatMessageImage source={source} style={{ width: 160, height: 120 }} />);

    fireEvent(view.UNSAFE_getByType(Image), 'error', { error: 'preview unavailable' });
    fireEvent(view.UNSAFE_getByType(Image), 'error', { error: 'original unavailable' });

    expect(view.getByLabelText('图片暂时无法加载，轻触重试')).toBeTruthy();
    expect(view.getByText('图片暂时无法加载')).toBeTruthy();
    fireEvent.press(view.getByLabelText('图片暂时无法加载，轻触重试'));

    expect(view.UNSAFE_getByType(Image).props.source.uri).toContain('variant=preview');
    expect(view.UNSAFE_getByType(Image).props.recyclingKey).toContain(':1');
  });
});
