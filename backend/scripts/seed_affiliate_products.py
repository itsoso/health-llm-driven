"""种子数据 — 常见补剂的 iHerb 联盟产品"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.affiliate_product import AffiliateProduct

PRODUCTS = [
    # ── 活性叶酸 (MTHFR) ──
    {"name": "Thorne 5-MTHF 活性叶酸 1mg 60粒", "brand": "Thorne", "supplement_name": "活性叶酸",
     "category": "basic", "keywords": ["叶酸", "5-MTHF", "甲基叶酸", "folate"],
     "platform": "iherb", "affiliate_url": "https://www.iherb.com/pr/thorne-5-mthf-1-mg-60-capsules/18473",
     "price_display": "$16.00", "currency": "USD",
     "gene_tags": ["MTHFR_TT", "MTHFR_CT"], "gene_description": "适合MTHFR C677T变异用户"},
    {"name": "Jarrow Methyl Folate 甲基叶酸 400mcg 60粒", "brand": "Jarrow", "supplement_name": "活性叶酸",
     "category": "basic", "keywords": ["叶酸", "甲基叶酸", "methyl folate"],
     "platform": "iherb", "affiliate_url": "https://www.iherb.com/pr/jarrow-formulas-methyl-folate-400-mcg-60-veggie-caps/41168",
     "price_display": "$8.49", "currency": "USD",
     "gene_tags": ["MTHFR_TT", "MTHFR_CT"], "gene_description": "适合MTHFR C677T变异用户"},

    # ── 维生素D3 (VDR) ──
    {"name": "Now Foods 维生素D3 5000IU 240粒", "brand": "Now Foods", "supplement_name": "维生素D3",
     "category": "basic", "keywords": ["维D", "维生素D", "VD3", "cholecalciferol"],
     "platform": "iherb", "affiliate_url": "https://www.iherb.com/pr/now-foods-vitamin-d-3-high-potency-125-mcg-5-000-iu-240-softgels/10421",
     "price_display": "$11.99", "currency": "USD",
     "gene_tags": ["VDR_TT"], "gene_description": "适合VDR基因变异、维D吸收不良用户"},
    {"name": "Thorne 维生素D/K2液体 1oz", "brand": "Thorne", "supplement_name": "维生素D3",
     "category": "basic", "keywords": ["维D", "维生素D", "D3K2"],
     "platform": "iherb", "affiliate_url": "https://www.iherb.com/pr/thorne-vitamin-d-k2-liquid-1-fl-oz-30-ml/80862",
     "price_display": "$26.00", "currency": "USD",
     "gene_tags": ["VDR_TT"], "gene_description": "D3+K2协同吸收，适合VDR变异用户"},

    # ── Omega-3 鱼油 ──
    {"name": "Nordic Naturals Ultimate Omega 1280mg 60粒", "brand": "Nordic Naturals", "supplement_name": "Omega-3",
     "category": "basic", "keywords": ["鱼油", "omega3", "EPA", "DHA", "深海鱼油"],
     "platform": "iherb", "affiliate_url": "https://www.iherb.com/pr/nordic-naturals-ultimate-omega-lemon-1-280-mg-60-soft-gels/6029",
     "price_display": "$27.46", "currency": "USD"},
    {"name": "California Gold 高浓度鱼油 240粒", "brand": "California Gold", "supplement_name": "Omega-3",
     "category": "basic", "keywords": ["鱼油", "omega3", "EPA", "DHA"],
     "platform": "iherb", "affiliate_url": "https://www.iherb.com/pr/california-gold-nutrition-omega-3-premium-fish-oil-240-fish-gelatin-softgels/93843",
     "price_display": "$14.00", "currency": "USD"},

    # ── B族维生素 ──
    {"name": "Thorne B-Complex #12 活性B族 60粒", "brand": "Thorne", "supplement_name": "维生素B族",
     "category": "basic", "keywords": ["B族", "B12", "复合维生素B", "B-complex"],
     "platform": "iherb", "affiliate_url": "https://www.iherb.com/pr/thorne-b-complex-12-60-capsules/18458",
     "price_display": "$19.00", "currency": "USD",
     "gene_tags": ["MTHFR_TT"], "gene_description": "含活性甲基B12，适合MTHFR变异用户"},

    # ── 镁 ──
    {"name": "Doctor's Best 甘氨酸镁 200mg 240粒", "brand": "Doctor's Best", "supplement_name": "镁",
     "category": "sleep", "keywords": ["镁", "甘氨酸镁", "magnesium glycinate"],
     "platform": "iherb", "affiliate_url": "https://www.iherb.com/pr/doctor-s-best-high-absorption-magnesium-100-mg-240-tablets/15",
     "price_display": "$18.74", "currency": "USD"},
    {"name": "Now Foods 柠檬酸镁 200mg 250粒", "brand": "Now Foods", "supplement_name": "镁",
     "category": "sleep", "keywords": ["镁", "柠檬酸镁", "magnesium citrate"],
     "platform": "iherb", "affiliate_url": "https://www.iherb.com/pr/now-foods-magnesium-citrate-200-mg-250-tablets/480",
     "price_display": "$12.99", "currency": "USD"},

    # ── NAC ──
    {"name": "Now Foods NAC 600mg 250粒", "brand": "Now Foods", "supplement_name": "NAC",
     "category": "antioxidant", "keywords": ["NAC", "N-乙酰半胱氨酸", "谷胱甘肽"],
     "platform": "iherb", "affiliate_url": "https://www.iherb.com/pr/now-foods-nac-600-mg-250-veg-capsules/17437",
     "price_display": "$18.99", "currency": "USD"},
    {"name": "Jarrow NAC Sustain 600mg 100粒", "brand": "Jarrow", "supplement_name": "NAC",
     "category": "antioxidant", "keywords": ["NAC", "N-乙酰半胱氨酸", "缓释"],
     "platform": "iherb", "affiliate_url": "https://www.iherb.com/pr/jarrow-formulas-n-a-c-sustain-n-acetyl-l-cysteine-600-mg-100-bilayer-tablets/1001",
     "price_display": "$14.49", "currency": "USD"},

    # ── 维生素C ──
    {"name": "California Gold 维生素C 1000mg 240粒", "brand": "California Gold", "supplement_name": "维生素C",
     "category": "immune", "keywords": ["维C", "VC", "抗坏血酸", "vitamin C"],
     "platform": "iherb", "affiliate_url": "https://www.iherb.com/pr/california-gold-nutrition-gold-c-vitamin-c-1-000-mg-240-veggie-capsules/61857",
     "price_display": "$10.00", "currency": "USD"},

    # ── 锌 ──
    {"name": "Now Foods 甘氨酸锌 30mg 120粒", "brand": "Now Foods", "supplement_name": "锌",
     "category": "immune", "keywords": ["锌", "甘氨酸锌", "zinc glycinate"],
     "platform": "iherb", "affiliate_url": "https://www.iherb.com/pr/now-foods-zinc-glycinate-120-softgels/68854",
     "price_display": "$8.99", "currency": "USD"},
    {"name": "Thorne 吡啶甲酸锌 15mg 60粒", "brand": "Thorne", "supplement_name": "锌",
     "category": "immune", "keywords": ["锌", "吡啶甲酸锌", "zinc picolinate"],
     "platform": "iherb", "affiliate_url": "https://www.iherb.com/pr/thorne-zinc-picolinate-15-mg-60-capsules/18585",
     "price_display": "$12.00", "currency": "USD"},

    # ── 辅酶Q10 ──
    {"name": "Doctor's Best 辅酶Q10 200mg 60粒", "brand": "Doctor's Best", "supplement_name": "辅酶Q10",
     "category": "antioxidant", "keywords": ["CoQ10", "辅酶Q10", "泛醇"],
     "platform": "iherb", "affiliate_url": "https://www.iherb.com/pr/doctor-s-best-high-absorption-coq10-with-bioperine-200-mg-60-veggie-caps/15",
     "price_display": "$14.99", "currency": "USD"},
]


def seed():
    db = SessionLocal()
    try:
        existing = db.query(AffiliateProduct).count()
        if existing > 0:
            print(f"已有 {existing} 个产品，跳过种子数据。用 --force 覆盖。")
            if "--force" not in sys.argv:
                return
            db.query(AffiliateProduct).delete()
            db.commit()
            print("已清空旧数据。")

        for p in PRODUCTS:
            db.add(AffiliateProduct(**p))
        db.commit()
        print(f"已插入 {len(PRODUCTS)} 个产品。")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
