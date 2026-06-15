-- 协议层用药打通:链接协议到具体业务记录(如 Medication.id),完成时写真实记录(MedicationLog)
ALTER TABLE health_protocols ADD COLUMN IF NOT EXISTS source_id INTEGER;
