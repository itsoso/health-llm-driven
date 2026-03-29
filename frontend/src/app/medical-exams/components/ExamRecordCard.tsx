'use client';

import { MedicalExam, examTypeLabels, bodySystemLabels, abnormalStyles, abnormalLabels } from './types';

interface ExamRecordCardProps {
  exam: MedicalExam;
  isExpanded: boolean;
  onToggle: () => void;
  abnormalCount: number;
}

export function ExamRecordCard({ exam, isExpanded, onToggle, abnormalCount }: ExamRecordCardProps) {
  return (
    <div className="bg-white rounded-xl shadow-md border border-gray-100 overflow-hidden">
      {/* 记录头部 */}
      <div
        className="p-4 cursor-pointer hover:bg-gray-50 transition-colors"
        onClick={onToggle}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 bg-teal-100 rounded-xl flex items-center justify-center">
              <span className="text-2xl">🩺</span>
            </div>
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-bold text-gray-900">{exam.exam_date}</span>
                {exam.patient_name && (
                  <span className="px-2 py-0.5 bg-purple-100 text-purple-700 rounded text-sm font-medium">
                    👤 {exam.patient_name}
                  </span>
                )}
                <span className="px-2 py-0.5 bg-teal-100 text-teal-700 rounded text-sm font-medium">
                  {examTypeLabels[exam.exam_type?.toLowerCase()] || exam.exam_type}
                </span>
                {exam.body_system && (
                  <span className="px-2 py-0.5 bg-gray-100 text-gray-600 rounded text-sm">
                    {bodySystemLabels[exam.body_system?.toLowerCase()] || exam.body_system}
                  </span>
                )}
              </div>
              <div className="text-sm text-gray-600 mt-1">
                {exam.hospital_name && <span>{exam.hospital_name}</span>}
                {exam.doctor_name && <span className="ml-2">• {exam.doctor_name}</span>}
                <span className="ml-2">• {exam.items.length} 项检查</span>
                {abnormalCount > 0 && (
                  <span className="ml-2 text-orange-600 font-medium">
                    ⚠️ {abnormalCount} 项异常
                  </span>
                )}
              </div>
            </div>
          </div>
          <div className="text-gray-400 text-2xl">
            {isExpanded ? '▲' : '▼'}
          </div>
        </div>
      </div>

      {/* 展开的详情 */}
      {isExpanded && (
        <div className="border-t border-gray-100 p-4 bg-gray-50">
          {/* 患者信息 */}
          {(exam.patient_name || exam.patient_gender || exam.patient_age || exam.exam_number) && (
            <div className="mb-4 p-3 bg-purple-50 rounded-lg border border-purple-100">
              <div className="text-sm font-semibold text-purple-800 mb-2">👤 患者信息</div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-sm">
                {exam.patient_name && (
                  <div><span className="text-gray-500">姓名:</span> <span className="text-gray-900 font-medium">{exam.patient_name}</span></div>
                )}
                {exam.patient_gender && (
                  <div><span className="text-gray-500">性别:</span> <span className="text-gray-900">{exam.patient_gender}</span></div>
                )}
                {exam.patient_age && (
                  <div><span className="text-gray-500">年龄:</span> <span className="text-gray-900">{exam.patient_age}岁</span></div>
                )}
                {exam.exam_number && (
                  <div><span className="text-gray-500">体检号:</span> <span className="text-gray-900">{exam.exam_number}</span></div>
                )}
              </div>
            </div>
          )}

          {exam.overall_assessment && (
            <div className="mb-4 p-3 bg-blue-50 rounded-lg border border-blue-100">
              <div className="text-sm font-semibold text-blue-800 mb-1">📋 总体评价</div>
              <div className="text-gray-800">{exam.overall_assessment}</div>
            </div>
          )}

          {/* 结论建议 */}
          {exam.conclusions && exam.conclusions.length > 0 && (
            <div className="mb-4 p-3 bg-amber-50 rounded-lg border border-amber-200">
              <div className="text-sm font-semibold text-amber-800 mb-2">⚠️ 检查结论与建议</div>
              <div className="space-y-2">
                {exam.conclusions.map((conclusion, idx) => {
                  const category = conclusion.category || conclusion.type || '';
                  const title = conclusion.title || '';
                  const rec = conclusion.recommendations || conclusion.recommendation || '';
                  return (
                    <div key={idx} className="p-3 bg-white rounded border border-amber-100">
                      <div className="flex items-start gap-2 mb-1">
                        {category && (
                          <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium shrink-0 ${
                            category.includes('attention') || category.includes('关注') ? 'bg-red-100 text-red-700' :
                            category.includes('followup') || category.includes('随诊') ? 'bg-yellow-100 text-yellow-700' :
                            'bg-blue-100 text-blue-700'
                          }`}>
                            {category.includes('attention') ? '需要关注' :
                             category.includes('followup') ? '定期随诊' :
                             category}
                          </span>
                        )}
                        {title && (
                          <span className="font-semibold text-gray-800">{title}</span>
                        )}
                      </div>
                      {conclusion.description && (
                        <div className="text-gray-700 text-sm mb-1">{conclusion.description}</div>
                      )}
                      {rec && (
                        <div className="text-teal-700 text-sm bg-teal-50 p-2 rounded mt-2">
                          💡 <span className="font-medium">建议:</span> {rec}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {exam.items.length > 0 ? (
            <div>
              <h4 className="font-bold text-gray-800 mb-3">检查项目明细</h4>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-gray-100">
                      <th className="text-left p-2 font-semibold text-gray-700">类别</th>
                      <th className="text-left p-2 font-semibold text-gray-700">项目名称</th>
                      <th className="text-right p-2 font-semibold text-gray-700">检测值</th>
                      <th className="text-left p-2 font-semibold text-gray-700">单位</th>
                      <th className="text-left p-2 font-semibold text-gray-700">参考范围</th>
                      <th className="text-center p-2 font-semibold text-gray-700">状态</th>
                    </tr>
                  </thead>
                  <tbody>
                    {exam.items.map((item) => (
                      <tr key={item.id} className="border-b border-gray-100 hover:bg-white">
                        <td className="p-2 text-gray-500 text-xs">
                          {examTypeLabels[item.category?.toLowerCase() || ''] || item.category || '-'}
                        </td>
                        <td className="p-2 font-medium text-gray-900">{item.item_name}</td>
                        <td className="p-2 text-right font-mono text-gray-900">
                          {item.value !== null && item.value !== undefined
                            ? item.value
                            : item.value_text || '-'}
                        </td>
                        <td className="p-2 text-gray-600">{item.unit || '-'}</td>
                        <td className="p-2 text-gray-600">{item.reference_range || '-'}</td>
                        <td className="p-2 text-center">
                          <span className={`px-2 py-0.5 rounded text-xs font-medium ${abnormalStyles[item.is_abnormal || 'normal']}`}>
                            {abnormalLabels[item.is_abnormal || 'normal']}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <p className="text-gray-500 text-center py-4">暂无检查项目明细</p>
          )}

          {exam.notes && (
            <div className="mt-4 p-3 bg-yellow-50 rounded-lg border border-yellow-100">
              <div className="text-sm font-semibold text-yellow-800 mb-1">📝 备注</div>
              <div className="text-gray-800">{exam.notes}</div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
