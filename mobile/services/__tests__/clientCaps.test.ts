import { REVA_UI_TABLE_CAP_ENABLED, buildClientCapsHeader } from '../clientCaps';

describe('client caps header', () => {
  it('enables the metric_table capability after the eval gate passed', () => {
    expect(REVA_UI_TABLE_CAP_ENABLED).toBe(true);
  });

  it('appends the metric_table token without changing existing capabilities', () => {
    expect(buildClientCapsHeader()).toBe(
      'genui-v1, genui-components-v1, genui-record-quality-v1, genui-table-v1',
    );
  });
});
