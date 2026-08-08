import {
  createVerifiedWriteReceipt,
  formatWriteReceipt,
  normalizeWriteReceipt,
  parseExecutedRef,
} from '../writeReceipt';

function serverReceipt(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    operation_id: 'health_manage:water_record:718',
    status: 'verified',
    resource_type: 'water_record',
    resource_id: '718',
    completed_at: '2026-08-08T21:28:00.000Z',
    verified: true,
    ...overrides,
  };
}

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

  it.each([
    'operation_id',
    'resource_type',
    'resource_id',
    'completed_at',
    'verified',
  ])('rejects an inherited required %s field', (field) => {
    const ownFields = serverReceipt();
    const inheritedValue = ownFields[field];
    delete ownFields[field];
    const raw = Object.assign(Object.create({ [field]: inheritedValue }), ownFields);

    expect(normalizeWriteReceipt(raw)).toBeUndefined();
  });

  it('ignores inherited optional receipt fields', () => {
    const raw = Object.assign(
      Object.create({ status: 'dismissed', action: 'delete', executed_ref: 'water_record:999' }),
      serverReceipt({ status: undefined }),
    );
    delete raw.status;

    expect(normalizeWriteReceipt(raw)).toEqual(expect.objectContaining({
      status: 'verified',
      resourceId: '718',
    }));
    expect(normalizeWriteReceipt(raw)).not.toHaveProperty('action');
    expect(normalizeWriteReceipt(raw)).not.toHaveProperty('executedRef');
  });

  it.each([
    ['operation_id', { value: 'health_manage:water_record:718' }],
    ['resource_type', { value: 'water_record' }],
    ['resource_id', { value: 718 }],
    ['completed_at', { value: '2026-08-08T21:28:00.000Z' }],
    ['action', { value: 'update' }],
    ['executed_ref', { value: 'water_record:718' }],
  ])('rejects a non-primitive %s field', (field, value) => {
    expect(normalizeWriteReceipt(serverReceipt({ [field]: value }))).toBeUndefined();
  });

  it('accepts a primitive numeric resource id', () => {
    expect(normalizeWriteReceipt(serverReceipt({ resource_id: 718 }))).toEqual(
      expect.objectContaining({ resourceId: '718' }),
    );
  });

  it.each(['verified', 'dismissed'] as const)(
    'accepts the explicit %s status',
    (status) => {
      expect(normalizeWriteReceipt(serverReceipt({ status }))).toEqual(
        expect.objectContaining({ status }),
      );
    },
  );

  it('treats a missing own status as a legacy verified receipt', () => {
    const raw = serverReceipt();
    delete raw.status;

    expect(normalizeWriteReceipt(raw)).toEqual(expect.objectContaining({ status: 'verified' }));
  });

  it.each(['failed', 'weird', null, undefined, { value: 'verified' }])(
    'rejects an explicit non-terminal status: %p',
    (status) => {
      expect(normalizeWriteReceipt(serverReceipt({ status }))).toBeUndefined();
    },
  );

  it.each(['constructor', 'toString', '__proto__'])(
    'uses the generic label for the dangerous resource type %s',
    (resourceType) => {
      expect(formatWriteReceipt({
        operationId: `health_manage:${resourceType}:718`,
        status: 'verified',
        resourceType,
        resourceId: '718',
        completedAt: '2026-08-08T21:28:00.000Z',
        verified: true,
        action: 'update',
      })).toBe('已更新 · 健康数据 #718');
    },
  );

  it.each(['update', 'delete'] as const)(
    'keeps dismissed status authoritative over the %s action',
    (action) => {
      expect(formatWriteReceipt({
        operationId: `health_manage:water_record:718:${action}`,
        status: 'dismissed',
        resourceType: 'water_record',
        resourceId: '718',
        completedAt: '2026-08-08T21:28:00.000Z',
        verified: true,
        action,
      })).toBe('已忽略 · 健康数据 #718');
    },
  );
});
