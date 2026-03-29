'use client';

import { MedicalExam } from './types';

interface StatsCardsProps {
  exams: MedicalExam[];
  getAbnormalCount: (exam: MedicalExam) => number;
}

export function StatsCards({ exams, getAbnormalCount }: StatsCardsProps) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
      <div className="bg-white p-4 rounded-xl shadow-md border border-teal-100">
        <p className="text-sm text-gray-600 mb-1">总体检次数</p>
        <p className="text-3xl font-bold text-teal-600">{exams.length}</p>
      </div>
      <div className="bg-white p-4 rounded-xl shadow-md border border-blue-100">
        <p className="text-sm text-gray-600 mb-1">检查项目</p>
        <p className="text-3xl font-bold text-blue-600">
          {exams.reduce((sum, exam) => sum + exam.items.length, 0)}
        </p>
      </div>
      <div className="bg-white p-4 rounded-xl shadow-md border border-orange-100">
        <p className="text-sm text-gray-600 mb-1">异常项目</p>
        <p className="text-3xl font-bold text-orange-600">
          {exams.reduce((sum, exam) => sum + getAbnormalCount(exam), 0)}
        </p>
      </div>
      <div className="bg-white p-4 rounded-xl shadow-md border border-green-100">
        <p className="text-sm text-gray-600 mb-1">最近体检</p>
        <p className="text-lg font-bold text-green-600">
          {exams.length > 0 ? exams[0].exam_date : '-'}
        </p>
      </div>
    </div>
  );
}
