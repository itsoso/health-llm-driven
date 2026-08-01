import React from 'react';
import { StyleSheet } from 'react-native';
import { render } from '@testing-library/react-native';

import { DietPrivacyRedactionOverlay } from '../DietPrivacyRedactionOverlay';

describe('DietPrivacyRedactionOverlay', () => {
  it('maps normalized points to fully opaque round black SVG paths', () => {
    const view = render(
      <DietPrivacyRedactionOverlay
        redactions={[{
          points: [{ x: 0.1, y: 0.2 }, { x: 0.5, y: 0.6 }, { x: 0.9, y: 0.8 }],
          width: 0.06,
        }]}
      />,
    );
    const path = view.getByTestId('Path');

    expect(path.props).toEqual(expect.objectContaining({
      d: 'M 0.1 0.2 L 0.5 0.6 L 0.9 0.8',
      fill: 'none',
      stroke: '#000000',
      strokeOpacity: 1,
      strokeWidth: 0.06,
      strokeLinecap: 'round',
      strokeLinejoin: 'round',
    }));
  });

  it('does not render empty, non-finite, out-of-range, zero-width, or stationary strokes', () => {
    const view = render(
      <DietPrivacyRedactionOverlay
        redactions={[
          { points: [], width: 0.06 },
          { points: [{ x: 0.2, y: 0.2 }], width: 0.06 },
          { points: [{ x: 0.2, y: 0.2 }, { x: Number.NaN, y: 0.4 }], width: 0.06 },
          { points: [{ x: -0.2, y: 0.2 }, { x: 0.4, y: 0.4 }], width: 0.06 },
          { points: [{ x: 0.2, y: 0.2 }, { x: 0.4, y: 0.4 }], width: 0 },
          { points: [{ x: 0.2, y: 0.2 }, { x: 0.2, y: 0.2 }], width: 0.06 },
        ]}
      />,
    );

    expect(view.queryAllByTestId('Path')).toHaveLength(0);
  });

  it('is an absolute non-interactive overlay', () => {
    const view = render(<DietPrivacyRedactionOverlay redactions={[]} />);
    const overlay = view.getByTestId('diet-share-privacy-overlay');

    expect(overlay.props.pointerEvents).toBe('none');
    expect(StyleSheet.flatten(overlay.props.style)).toEqual(expect.objectContaining({
      position: 'absolute',
      top: 0,
      right: 0,
      bottom: 0,
      left: 0,
    }));
  });
});
