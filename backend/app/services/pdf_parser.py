"""PDF解析服务 - 解析体检报告PDF并结构化保存"""
import os
import json
import logging
import tempfile
from typing import Optional, Dict, Any, List
from datetime import date
import pdfplumber
from openai import OpenAI
from app.config import settings
from app.services.exam_packages import normalize_item_name, identify_package, ITEM_LABELS

logger = logging.getLogger(__name__)


class MedicalReportPDFParser:
    """体检报告PDF解析器"""
    
    def __init__(self):
        self.client = None
        if settings.openai_api_key:
            self.client = OpenAI(api_key=settings.openai_api_key)
    
    def extract_text_from_pdf(self, pdf_path: str) -> str:
        """从PDF中提取文本"""
        text_content = []
        
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page_num, page in enumerate(pdf.pages, 1):
                    page_text = page.extract_text()
                    if page_text:
                        text_content.append(f"--- 第{page_num}页 ---\n{page_text}")
                    
                    # 尝试提取表格
                    tables = page.extract_tables()
                    for table_idx, table in enumerate(tables):
                        if table:
                            table_text = self._format_table(table)
                            text_content.append(f"\n[表格 {table_idx + 1}]\n{table_text}")
        except Exception as e:
            logger.error(f"PDF解析失败: {e}")
            raise ValueError(f"PDF解析失败: {str(e)}")
        
        return "\n".join(text_content)
    
    def _format_table(self, table: List[List[str]]) -> str:
        """格式化表格为文本"""
        lines = []
        for row in table:
            if row:
                cleaned_row = [str(cell).strip() if cell else "" for cell in row]
                lines.append(" | ".join(cleaned_row))
        return "\n".join(lines)
    
    def parse_with_llm(self, text_content: str) -> Dict[str, Any]:
        """使用LLM解析体检报告文本"""
        if not self.client:
            raise ValueError("LLM服务不可用，请配置OpenAI API Key")
        
        prompt = """你是一个专业的医疗报告解析专家。请解析以下体检报告内容，提取结构化数据。

请严格按照以下JSON格式返回结果（不要包含任何其他文字，只返回JSON）：

{{
    "patient_name": "患者姓名",
    "patient_gender": "性别(male/female)",
    "patient_age": 年龄数字,
    "exam_date": "YYYY-MM-DD格式的体检日期",
    "exam_number": "体检号",
    "exam_type": "comprehensive",
    "hospital_name": "医院名称",
    "doctor_name": "医生姓名（如果有）",
    "overall_assessment": "总体评价摘要",
    "conclusions": [
        {{
            "category": "分类(urgent_attention/needs_attention/regular_followup/normal)",
            "title": "结论标题",
            "description": "详细描述",
            "recommendations": "建议措施"
        }}
    ],
    "items": [
        {{
            "category": "检查类别(blood_routine/lipid_profile/blood_glucose/urine_routine/liver_function/kidney_function/immune/tumor_marker/thyroid/ultrasound/brain_ct/chest_ct/abdominal_ct/ct/mri/ecg/echocardiography/eye/ent/body_composition/physical/internal_medicine/surgery/other)",
            "item_name": "检查项目名称",
            "value": 数值或null,
            "value_text": "文本值（如影像结论）",
            "unit": "单位",
            "reference_range": "参考范围",
            "is_abnormal": "normal/high/low/abnormal",
            "notes": "备注说明"
        }}
    ]
}}

检查类别说明（请使用以下标准类别名称）：
【血液检查】
- blood_routine: 血常规（白细胞、红细胞、血红蛋白、血小板、中性粒细胞、淋巴细胞等）
- lipid_profile: 血脂（总胆固醇、甘油三酯、高密度脂蛋白、低密度脂蛋白、载脂蛋白A1、载脂蛋白B等）
- blood_glucose: 血糖（空腹血糖、糖化血红蛋白HbA1c、糖化白蛋白等）
- urine_routine: 尿常规
- stool_routine: 大便常规（含隐血OB）

【生化检查】
- liver_function: 肝功能（谷丙转氨酶ALT、谷草转氨酶AST、谷氨酰转肽酶GGT、总胆红素、白蛋白等）
- kidney_function: 肾功能（肌酐、尿素氮、尿酸、胱抑素C等）
- electrolyte: 电解质（钾、钠、氯、钙、镁、磷等）
- cardiac_enzyme: 心肌酶谱（CK、CK-MB、LDH、肌红蛋白、肌钙蛋白I/T、BNP等）

【免疫检查】
- immune: 免疫功能（CD3、CD4、CD8、CD16、CD19、CD45、CD56、NK细胞、B淋巴细胞、T细胞亚群10CD分析等）
- tumor_marker: 肿瘤标志物（AFP、CEA、CA199、CA125、CA153、PSA、FPSA、SCC、CYFRA21-1、NSE、HE4等）
- autoimmune: 自身免疫抗体

【内分泌检查】
- thyroid: 甲状腺功能（TSH、FT3、FT4、TT3、TT4、TPOAb、TgAb等甲功全套）
- hormone: 激素检查（性激素、皮质醇、空腹胰岛素、C肽等）
- bone_metabolism: 骨代谢（25羟维生素D、PTH、骨钙素等）

【影像学检查】
- ultrasound: 超声检查（肝胆脾胰超声、甲状腺超声、泌尿系超声、心脏彩超等）
- brain_ct: 脑部CT
- chest_ct: 胸部CT/肺部CT
- abdominal_ct: 腹部CT
- ct: 其他CT检查
- mri: MRI/磁共振检查
- xray: X光/胸片

【心电检查】
- ecg: 心电图
- echocardiography: 心脏彩超/超声心动图

【专科检查】
- eye: 眼科检查（视力、眼底、眼压等）
- ent: 耳鼻喉科（听力、鼻咽、喉部等）
- dental: 口腔科
- gynecology: 妇科检查

【体格检查】
- body_composition: 人体成分/体成分（身高、体重、BMI、体脂率、腹围等）
- physical: 一般检查（血压、脉搏等）
- internal_medicine: 内科检查
- surgery: 外科检查

- other: 其他无法分类的项目

注意：
1. 日期格式必须是 YYYY-MM-DD
2. value 为数字时不含单位，非数值项目使用 value_text
3. is_abnormal 根据检测值和参考范围判断
4. 尽可能提取所有检查项目，包括血常规、肝功能、免疫功能、影像学检查等
5. conclusions 提取总检结论中的各个分类（需要关注、定期随诊等）

体检报告内容：
{text}
"""
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "你是专业的医疗报告解析专家，擅长从体检报告中提取结构化数据。只返回JSON格式，不要包含任何解释性文字。"
                    },
                    {
                        "role": "user",
                        "content": prompt.format(text=text_content[:8000])  # 限制长度
                    }
                ],
                temperature=0.1,
                max_tokens=4000
            )
            
            result_text = response.choices[0].message.content
            if not result_text:
                raise ValueError("LLM返回内容为空")
            
            result_text = result_text.strip()
            logger.info(f"LLM原始返回长度: {len(result_text)}, 前500字符: {result_text[:500]}...")
            
            # 尝试提取JSON部分
            json_text = result_text
            
            # 处理markdown代码块
            if "```json" in json_text:
                json_text = json_text.split("```json")[1].split("```")[0]
            elif "```" in json_text:
                parts = json_text.split("```")
                if len(parts) >= 2:
                    json_text = parts[1]
                    # 移除可能的语言标识符
                    lines = json_text.split('\n')
                    if lines and lines[0].strip().lower() in ['json', 'javascript', 'js']:
                        json_text = '\n'.join(lines[1:])
            
            # 去除首尾空白
            json_text = json_text.strip()
            
            # 查找JSON对象的开始和结束（处理嵌套括号）
            start_idx = json_text.find('{')
            if start_idx == -1:
                raise ValueError("未找到JSON对象开始标记 '{'")
            
            # 计算匹配的结束括号
            brace_count = 0
            end_idx = -1
            for i, char in enumerate(json_text[start_idx:], start_idx):
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end_idx = i
                        break
            
            if end_idx == -1:
                # 退而求其次，使用最后一个 }
                end_idx = json_text.rfind('}')
            
            if end_idx != -1 and end_idx >= start_idx:
                json_text = json_text[start_idx:end_idx + 1]
            else:
                raise ValueError("无法提取有效的JSON对象")
            
            logger.info(f"清理后的JSON长度: {len(json_text)}, 前300字符: {json_text[:300]}...")
            
            # 尝试解析JSON
            try:
                parsed_data = json.loads(json_text)
            except json.JSONDecodeError as je:
                # 尝试修复常见问题
                # 1. 移除控制字符
                import re
                cleaned = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', json_text)
                # 2. 修复可能的尾部逗号
                cleaned = re.sub(r',\s*}', '}', cleaned)
                cleaned = re.sub(r',\s*]', ']', cleaned)
                parsed_data = json.loads(cleaned)
            
            return parsed_data
            
        except json.JSONDecodeError as e:
            logger.error(f"LLM返回的JSON解析失败: {e}")
            logger.error(f"原始返回内容: {result_text[:1000] if 'result_text' in locals() else 'N/A'}")
            logger.error(f"清理后内容: {json_text[:1000] if 'json_text' in locals() else 'N/A'}")
            raise ValueError(f"解析结果格式错误，请重试。详情: {str(e)[:100]}")
        except Exception as e:
            logger.error(f"LLM解析失败: {e}", exc_info=True)
            raise ValueError(f"LLM解析失败，请重试")
    
    def parse_pdf(self, pdf_path: str) -> Dict[str, Any]:
        """完整解析PDF体检报告"""
        # 1. 提取PDF文本
        text_content = self.extract_text_from_pdf(pdf_path)
        
        if not text_content.strip():
            raise ValueError("PDF内容为空或无法提取文本")
        
        # 2. 使用LLM解析
        parsed_data = self.parse_with_llm(text_content)
        
        # 3. 验证和清理数据
        return self._validate_and_clean(parsed_data)
    
    def _validate_and_clean(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """验证和清理解析结果"""
        # 确保必要字段存在
        if not data.get("exam_date"):
            data["exam_date"] = date.today().isoformat()
        
        if not data.get("exam_type"):
            data["exam_type"] = "other"
        
        # 清理items，并标准化项目名称
        cleaned_items = []
        item_codes = []  # 收集所有项目代码用于套餐识别
        
        for item in data.get("items", []):
            if item.get("item_name"):
                original_name = str(item["item_name"]).strip()
                
                # 尝试标准化项目名称
                item_code, standard_name = normalize_item_name(original_name)
                
                cleaned_item = {
                    "category": item.get("category") or None,
                    "item_name": standard_name,  # 使用标准化名称
                    "item_code": item_code or item.get("item_code") or None,  # 添加项目代码
                    "value": self._safe_float(item.get("value")),
                    "value_text": item.get("value_text") or None,
                    "unit": item.get("unit") or None,
                    "reference_range": item.get("reference_range") or None,
                    "is_abnormal": item.get("is_abnormal", "normal"),
                    "notes": item.get("notes") or None
                }
                cleaned_items.append(cleaned_item)
                
                if item_code:
                    item_codes.append(item_code)
        
        data["items"] = cleaned_items
        
        # 尝试识别包含的体检套餐
        if item_codes:
            matched_packages = identify_package(item_codes)
            if matched_packages:
                data["identified_packages"] = matched_packages
                logger.info(f"识别到体检套餐: {matched_packages}")
        
        return data
    
    def _safe_float(self, value) -> Optional[float]:
        """安全转换为浮点数"""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None


# 单例实例
pdf_parser = MedicalReportPDFParser()

