'use client';

import { useState, useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import ProtectedRoute from '@/components/ProtectedRoute';
import { familyApi } from '@/services/api';

interface Medication {
  id: number;
  name: string;
  category: string | null;
  dosage: string | null;
  frequency: string | null;
  purpose: string | null;
  notes: string | null;
  start_date: string | null;
  taken_today: boolean;
}

export default function MedicationsPage() {
  return <ProtectedRoute><MedicationsContent /></ProtectedRoute>;
}

function MedicationsContent() {
  const router = useRouter();
  const [meds, setMeds] = useState<Medication[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [recognizing, setRecognizing] = useState(false);
  const [addForm, setAddForm] = useState({ name: '', dosage: '', frequency: '', purpose: '', notes: '' });
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => { loadMeds(); }, []);

  const loadMeds = async () => {
    setLoading(true);
    try {
      const res = await familyApi.getMedications();
      setMeds(res.data.medications || []);
    } catch { } finally { setLoading(false); }
  };

  const takeMed = async (id: number) => {
    try {
      await familyApi.takeMedication(id);
      await loadMeds();
    } catch (e: any) {
      alert(e.response?.data?.detail || '记录失败');
    }
  };

  const addMed = async () => {
    if (!addForm.name.trim()) return;
    try {
      await familyApi.addMedication(addForm);
      setShowAdd(false);
      setAddForm({ name: '', dosage: '', frequency: '', purpose: '', notes: '' });
      await loadMeds();
    } catch (e: any) {
      alert(e.response?.data?.detail || '添加失败');
    }
  };

  const recognizeFromPhoto = async (file: File) => {
    setRecognizing(true);
    try {
      const base64 = await fileToBase64(file);
      const res = await familyApi.recognizeMedication(base64);
      alert(`已识别并添加: ${res.data.recognized?.name || '未知药品'}`);
      await loadMeds();
    } catch (e: any) {
      alert('识别失败: ' + (e.response?.data?.detail || e.message));
    } finally {
      setRecognizing(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="bg-white border-b px-4 py-3 flex items-center gap-3">
        <button onClick={() => router.push('/family')} className="text-gray-500">← </button>
        <h1 className="font-bold text-lg">💊 用药管理</h1>
      </div>

      <div className="p-4 space-y-3">
        {/* 操作按钮 */}
        <div className="flex gap-2">
          <button onClick={() => fileRef.current?.click()} disabled={recognizing} className="flex-1 bg-green-500 text-white rounded-xl py-3 text-sm font-medium disabled:opacity-50">
            {recognizing ? '识别中...' : '📸 拍药盒识别'}
          </button>
          <button onClick={() => setShowAdd(true)} className="flex-1 bg-blue-500 text-white rounded-xl py-3 text-sm font-medium">
            ✏️ 手动添加
          </button>
          <input ref={fileRef} type="file" accept="image/*" capture="environment" className="hidden" onChange={e => { if (e.target.files?.[0]) recognizeFromPhoto(e.target.files[0]); }} />
        </div>

        {/* 添加表单 */}
        {showAdd && (
          <div className="bg-white rounded-xl p-4 shadow-sm border space-y-2">
            <input className="w-full border rounded-lg px-3 py-2 text-sm" placeholder="药品名称 *" value={addForm.name} onChange={e => setAddForm({ ...addForm, name: e.target.value })} />
            <div className="flex gap-2">
              <input className="flex-1 border rounded-lg px-3 py-2 text-sm" placeholder="剂量（如 5mg）" value={addForm.dosage} onChange={e => setAddForm({ ...addForm, dosage: e.target.value })} />
              <input className="flex-1 border rounded-lg px-3 py-2 text-sm" placeholder="频次（如 每日1次）" value={addForm.frequency} onChange={e => setAddForm({ ...addForm, frequency: e.target.value })} />
            </div>
            <input className="w-full border rounded-lg px-3 py-2 text-sm" placeholder="适应症" value={addForm.purpose} onChange={e => setAddForm({ ...addForm, purpose: e.target.value })} />
            <input className="w-full border rounded-lg px-3 py-2 text-sm" placeholder="注意事项" value={addForm.notes} onChange={e => setAddForm({ ...addForm, notes: e.target.value })} />
            <div className="flex gap-2">
              <button onClick={() => setShowAdd(false)} className="flex-1 border rounded-lg py-2 text-sm">取消</button>
              <button onClick={addMed} className="flex-1 bg-blue-500 text-white rounded-lg py-2 text-sm">添加</button>
            </div>
          </div>
        )}

        {/* 用药清单 */}
        {loading ? (
          <div className="text-center py-8 text-gray-400">加载中...</div>
        ) : meds.length === 0 ? (
          <div className="text-center py-12 text-gray-400">
            <div className="text-4xl mb-2">💊</div>
            <p>暂无用药记录</p>
            <p className="text-xs mt-1">拍药盒或手动添加</p>
          </div>
        ) : (
          meds.map(m => (
            <div key={m.id} className="bg-white rounded-xl p-4 shadow-sm border">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-medium">{m.name}</h3>
                  <div className="text-xs text-gray-400 mt-1">
                    {[m.dosage, m.frequency, m.purpose].filter(Boolean).join(' · ')}
                  </div>
                  {m.notes && <div className="text-xs text-amber-600 mt-1">⚠️ {m.notes}</div>}
                </div>
                <button
                  onClick={() => !m.taken_today && takeMed(m.id)}
                  className={`rounded-full w-10 h-10 flex items-center justify-center text-lg ${m.taken_today ? 'bg-green-100 text-green-600' : 'bg-gray-100 text-gray-400 hover:bg-blue-100'}`}
                >
                  {m.taken_today ? '✅' : '○'}
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      resolve(result.split(',')[1]); // 去掉 data:image/xxx;base64, 前缀
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}
