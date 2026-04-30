-- Concierge: 保健医生邮箱字段 (Doctor Weekly Report 优先发 email)
ALTER TABLE users ADD COLUMN IF NOT EXISTS doctor_email VARCHAR(200);
