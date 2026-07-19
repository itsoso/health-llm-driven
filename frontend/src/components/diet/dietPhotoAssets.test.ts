import { describe, expect, it } from 'vitest';

import { dietRecordPhotoUrls } from './dietPhotoAssets';

describe('dietRecordPhotoUrls', () => {
  it('uses ordered photo assets before legacy image fields', () => {
    expect(dietRecordPhotoUrls({
      image_url: 'https://legacy.example/cover.jpg',
      image_urls: ['https://legacy.example/cover.jpg', 'https://legacy.example/second.jpg'],
      photo_assets: [
        { ordinal: 2, url: 'https://assets.example/third.jpg' },
        { ordinal: 0, url: 'https://assets.example/first.jpg' },
        { ordinal: 1, url: 'https://assets.example/second.jpg' },
      ],
    })).toEqual([
      'https://assets.example/first.jpg',
      'https://assets.example/second.jpg',
      'https://assets.example/third.jpg',
    ]);
  });

  it('falls back to legacy URLs and removes empty or duplicated values', () => {
    expect(dietRecordPhotoUrls({
      image_urls: [' https://example.test/a.jpg ', '', 'https://example.test/a.jpg'],
      image_url: 'https://example.test/b.jpg',
    })).toEqual([
      'https://example.test/a.jpg',
      'https://example.test/b.jpg',
    ]);
  });
});
