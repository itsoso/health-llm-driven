import {
  REVA_UI_TABLE_CAP_ENABLED,
  REVA_UI_DIET_SUMMARY_CAP_ENABLED,
  REVA_UI_SLEEP_SUMMARY_CAP_ENABLED,
  REVA_UI_MEDICATION_LIST_CAP_ENABLED,
  buildClientCapsHeader,
} from '../clientCaps';

describe('client caps header', () => {
  it('enables the metric_table capability after the eval gate passed', () => {
    expect(REVA_UI_TABLE_CAP_ENABLED).toBe(true);
  });

  it('enables the diet_daily_summary capability after the eval gate passed', () => {
    expect(REVA_UI_DIET_SUMMARY_CAP_ENABLED).toBe(true);
  });

  it('enables the sleep_summary capability after the eval gate passed', () => {
    expect(REVA_UI_SLEEP_SUMMARY_CAP_ENABLED).toBe(true);
  });

  it('enables the medication_list capability after the eval gate passed', () => {
    expect(REVA_UI_MEDICATION_LIST_CAP_ENABLED).toBe(true);
  });

  it('appends lit GenUI tokens after the base caps, in declaration order', () => {
    expect(buildClientCapsHeader()).toBe(
      'genui-v1, genui-components-v1, genui-record-quality-v1, genui-table-v1, genui-diet-summary-v1, genui-sleep-summary-v1, genui-medication-list-v1',
    );
  });
});
