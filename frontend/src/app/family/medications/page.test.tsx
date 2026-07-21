// @vitest-environment jsdom
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { getMedications, recognizeMedication, addMedication } = vi.hoisted(() => ({
  getMedications: vi.fn(),
  recognizeMedication: vi.fn(),
  addMedication: vi.fn(),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock('@/components/ProtectedRoute', () => ({
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock('@/services/api/family', () => ({
  familyApi: {
    getMedications,
    recognizeMedication,
    addMedication,
    takeMedication: vi.fn(),
  },
}));

import MedicationsPage from './page';

describe('MedicationsPage medication recognition', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getMedications.mockResolvedValue({ data: { medications: [] } });
    vi.stubGlobal('alert', vi.fn());
    vi.stubGlobal('FileReader', class {
      result = 'data:image/jpeg;base64,aGVsbG8=';
      onload: null | (() => void) = null;
      onerror: null | (() => void) = null;

      readAsDataURL() {
        this.onload?.();
      }
    });
  });

  it('shows a retryable error instead of an empty list when loading fails', async () => {
    getMedications.mockRejectedValue(new Error('offline'));

    render(<MedicationsPage />);

    expect(await screen.findByText('用药清单加载失败')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '重试' })).toBeInTheDocument();
    expect(screen.queryByText('暂无用药记录')).not.toBeInTheDocument();
  });

  it('requires an editable confirmation before saving recognized medication', async () => {
    recognizeMedication.mockResolvedValue({
      data: {
        recognized: {
          name: '替普瑞酮胶囊',
          dosage: '50mg',
          frequency: '每日3次',
          indication: '胃黏膜保护',
          notes: '请核对处方',
        },
        requires_confirmation: true,
      },
    });
    addMedication.mockResolvedValue({ data: { id: 7 } });

    const { container } = render(<MedicationsPage />);
    const fileInput = container.querySelector('input[type="file"]');
    expect(fileInput).not.toBeNull();

    fireEvent.change(fileInput!, {
      target: { files: [new File(['image'], 'medicine.jpg', { type: 'image/jpeg' })] },
    });

    expect(await screen.findByText('核对识别结果')).toBeInTheDocument();
    expect(screen.getByDisplayValue('替普瑞酮胶囊')).toBeInTheDocument();
    expect(screen.getByDisplayValue('50mg')).toBeInTheDocument();
    expect(screen.getByDisplayValue('每日3次')).toBeInTheDocument();
    expect(screen.getByDisplayValue('胃黏膜保护')).toBeInTheDocument();
    expect(addMedication).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: '确认添加' }));

    await waitFor(() => expect(addMedication).toHaveBeenCalledWith({
      name: '替普瑞酮胶囊',
      dosage: '50mg',
      frequency: '每日3次',
      category: '',
      purpose: '胃黏膜保护',
      notes: '请核对处方',
    }));
  });
});
