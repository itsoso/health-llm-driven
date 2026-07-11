import {
  createVerifiedWriteReceipt,
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
});
