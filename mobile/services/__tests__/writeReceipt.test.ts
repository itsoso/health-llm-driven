import {
  createVerifiedWriteReceipt,
  formatWriteReceipt,
  normalizeWriteReceipt,
  parseExecutedRef,
} from '../writeReceipt';

describe('writeReceipt', () => {
  it('creates a verified receipt from a persisted resource id', () => {
    expect(createVerifiedWriteReceipt({
      operationId: 'diet_record.create:77',
      resourceType: 'diet_record',
      resourceId: 77,
      completedAt: '2026-07-09T12:00:00.000Z',
    })).toEqual({
      operationId: 'diet_record.create:77',
      status: 'verified',
      resourceType: 'diet_record',
      resourceId: '77',
      completedAt: '2026-07-09T12:00:00.000Z',
      verified: true,
    });
  });

  it('derives resource identity from a WriteIntent executed_ref', () => {
    expect(parseExecutedRef('smart_reminder:18')).toEqual({
      resourceType: 'smart_reminder',
      resourceId: '18',
    });
    expect(createVerifiedWriteReceipt({
      operationId: 'write_intent.confirm:42',
      executedRef: 'smart_reminder:18',
      completedAt: '2026-07-09T12:00:00.000Z',
    })).toEqual(expect.objectContaining({
      executedRef: 'smart_reminder:18',
      resourceType: 'smart_reminder',
      resourceId: '18',
      verified: true,
    }));
  });

  it('fails closed when no resource identity is present', () => {
    expect(() => createVerifiedWriteReceipt({
      operationId: 'agenda.complete:7',
      completedAt: '2026-07-09T12:00:00.000Z',
    })).toThrow('write_receipt_missing_identity');
  });

  it.each(['create', 'update', 'delete'] as const)(
    'normalizes the supported %s receipt action',
    (action) => {
      expect(normalizeWriteReceipt({
        operation_id: `health_manage:water_record:718:${action}`,
        status: 'verified',
        resource_type: 'water_record',
        resource_id: '718',
        completed_at: '2026-08-08T21:28:00.000Z',
        verified: true,
        action,
      })).toEqual(expect.objectContaining({ action }));
    },
  );

  it('drops an unsupported receipt action instead of trusting it', () => {
    const receipt = normalizeWriteReceipt({
      operation_id: 'health_manage:water_record:718',
      status: 'verified',
      resource_type: 'water_record',
      resource_id: '718',
      completed_at: '2026-08-08T21:28:00.000Z',
      verified: true,
      action: 'replace',
    });

    expect(receipt).toBeDefined();
    expect(receipt).not.toHaveProperty('action');
    expect(formatWriteReceipt(receipt!)).toBe('已写入 · 健康数据 #718');
  });

  it('formats verified update and delete receipts with their actual action', () => {
    const base = {
      operationId: 'health_manage:water_record:718',
      status: 'verified' as const,
      resourceType: 'water_record',
      resourceId: '718',
      completedAt: '2026-08-08T21:28:00.000Z',
      verified: true as const,
    };

    expect(formatWriteReceipt({ ...base, action: 'update' })).toBe('已更新 · 健康数据 #718');
    expect(formatWriteReceipt({ ...base, action: 'delete' })).toBe('已删除 · 健康数据 #718');
  });

  it('preserves diet-specific create and legacy receipt labels', () => {
    const dietBase = {
      operationId: 'health_record:diet_record:701',
      status: 'verified' as const,
      resourceType: 'diet_record',
      resourceId: '701',
      completedAt: '2026-08-08T08:00:00.000Z',
      verified: true as const,
    };

    expect(formatWriteReceipt({ ...dietBase, action: 'create' })).toBe(
      '已保存到今日饮食 · 记录 #701',
    );
    expect(formatWriteReceipt(dietBase)).toBe('已保存到今日饮食 · 记录 #701');
  });
});
