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

{
    "exam_date": "YYYY-MM-DD格式的体检日期",
    "exam_type": "体检类型，可选值: blood_routine(血常规), lipid_profile(血脂), urine_routine(尿常规), immune(免疫), liver_function(肝功能), kidney_function(肾功能), thyroid(甲状腺), other(其他)",
    "body_system": "身体系统，可选值: nervous(神经), circulatory(循环), respiratory(呼吸), digestive(消化), urinary(泌尿), endocrine(内分泌), immune(免疫), skeletal(骨骼), muscular(肌肉), other(其他)",
    "hospital_name": "医院名称",
    "doctor_name": "医生姓名（如果有）",
    "overall_assessment": "总体评价或结论",
    "items": [
        {
            "item_name": "检查项目名称",
            "value": 数值（纯数字，不含单位）,
            "unit": "单位",
            "reference_range": "参考范围",
            "is_abnormal": "normal/high/low/abnormal"
        }
    ]
}

注意：
1. 日期格式必须是 YYYY-MM-DD
2. value 必须是数字或 null
3. is_abnormal 根据检测值和参考范围判断：正常为normal，偏高为high，偏低为low，其他异常为abnormal
4. 如果某个字段无法从报告中提取，设置为 null
5. 尽可能提取所有检查项目

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
            
            result_text = response.choices[0].message.content.strip()
            logger.info(f"LLM原始返回: {result_text[:500]}...")
            
            # 尝试提取JSON部分
            json_text = result_text
            
            # 处理markdown代码块
            if "```json" in json_text:
                json_text = json_text.split("```json")[1].split("```")[0].strip()
            elif "```" in json_text:
                parts = json_text.split("```")
                if len(parts) >= 2:
                    json_text = parts[1].strip()
                    # 移除可能的语言标识符
                    if json_text.startswith("json"):
                        json_text = json_text[4:].strip()
            
            # 查找JSON对象的开始和结束
            start_idx = json_text.find('{')
            end_idx = json_text.rfind('}')
            
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                json_text = json_text[start_idx:end_idx + 1]
            
            logger.info(f"清理后的JSON: {json_text[:300]}...")
            
            parsed_data = json.loads(json_text)
            return parsed_data
            
        except json.JSONDecodeError as e:
            logger.error(f"LLM返回的JSON解析失败: {e}")
            logger.error(f"原始返回内容: {result_text[:1000] if 'result_text' in locals() else 'N/A'}")
            logger.error(f"清理后内容: {json_text[:1000] if 'json_text' in locals() else 'N/A'}")
            raise ValueError(f"解析结果格式错误，请重试")
        except Exception as e:
            logger.error(f"LLM解析失败: {e}", exc_info=True)
            raise ValueError(f"LLM解析失败: {str(e)}")
    
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
        
        # 清理items
        cleaned_items = []
        for item in data.get("items", []):
            if item.get("item_name"):
                cleaned_item = {
                    "item_name": str(item["item_name"]).strip(),
                    "value": self._safe_float(item.get("value")),
                    "unit": item.get("unit") or None,
                    "reference_range": item.get("reference_range") or None,
                    "is_abnormal": item.get("is_abnormal", "normal"),
                    "notes": item.get("notes") or None
                }
                cleaned_items.append(cleaned_item)
        
        data["items"] = cleaned_items
        
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

