import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import SharedMessageImages, { parseSharedImageUrls } from './SharedMessageImages';

describe('shared conversation images', () => {
  it('parses a persisted JSON image-url list', () => {
    expect(parseSharedImageUrls('["https://cdn.example/a.jpg", " https://cdn.example/b.jpg "]')).toEqual([
      'https://cdn.example/a.jpg',
      'https://cdn.example/b.jpg',
    ]);
  });

  it('renders shared message photos', () => {
    render(<SharedMessageImages imageUrl='["https://cdn.example/meal.jpg"]' />);

    const image = screen.getByRole('img', { name: '对话图片 1' });
    expect(image).toHaveAttribute('src', 'https://cdn.example/meal.jpg');
  });
});
