import { REVA_UI_TABLE_CAP_ENABLED, buildClientCapsHeader } from '../clientCaps';

describe('client caps header', () => {
  it('ships the metric_table renderer with the cap dark by default', () => {
    expect(REVA_UI_TABLE_CAP_ENABLED).toBe(false);
  });

  it('with cap dark, header is byte-for-byte the historical string', () => {
    // Regression guard: flipping the renderer in must NOT change the wire header
    // until REVA_UI_TABLE_CAP_ENABLED is intentionally flipped after eval passes.
    expect(buildClientCapsHeader()).toBe(
      'genui-v1, genui-components-v1, genui-record-quality-v1',
    );
    expect(buildClientCapsHeader()).not.toContain('genui-table-v1');
  });
});
