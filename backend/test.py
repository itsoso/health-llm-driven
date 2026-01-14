import os
from PIL import Image, ImageDraw, ImageFont

def create_long_image():
    # 1. 基础设置
    width = 1080
    # 为了长图不至于太长导致显存爆掉，这里适当缩减高度示例
    header_height = 500
    section_gap = 40
    card_height = 450
    footer_height = 200
    
    # 2. 颜色定义
    bg_color = "#FFF5E6" 
    header_bg = "#FF5000" 
    blue_card = "#E6F0FF" 
    blue_title = "#0056D2" 
    orange_card = "#FFF0E6" 
    orange_title = "#FF5000" 
    text_color = "#333333"
    
    policies = [
        {"title": "1 | 加大来客力 (新增)", "type": "blue", "content": "全链路流量升级：首月完成任务直送2万曝光"},
        {"title": "2 | 加码短视频 (升级)", "type": "blue", "content": "首条即起量，挂车缩短交易路径"},
        {"title": "3 | 加码直播 (升级)", "type": "blue", "content": "首播榜单+积分任务，持续开播有流量"},
        {"title": "4 | 加码商城 (升级)", "type": "blue", "content": "入驻经营任务化，装修/活动报名拿流量"},
        {"title": "=== 重磅减负 · 真金白银 ===", "type": "header", "content": ""},
        {"title": "5 | 免佣降本 (新增)", "type": "orange", "content": "首月免佣 + 返佣50% (封顶5000元)"},
        {"title": "6 | 商品卡免佣 (新增)", "type": "orange", "content": "技术服务费仅保留0.6%！(冷启/温饱两档)"},
        {"title": "7 | 首销激励 (新增)", "type": "orange", "content": "首单返现 + T90斗金最高返4万元"},
        {"title": "8 | 跃迁激励 (新增)", "type": "orange", "content": "90天内GMV达标，领万元磁力金牛券"},
        {"title": "9 | 经营保障 (升级)", "type": "blue", "content": "0保证金入驻 + 新手期免考 + 违规免责"},
    ]

    total_height = header_height + (len(policies) * (card_height + section_gap)) + footer_height
    
    img = Image.new('RGB', (width, total_height), bg_color)
    draw = ImageDraw.Draw(img)
    
    # -----------------------------------------------------------
    # 3. 字体加载核心修复逻辑
    # -----------------------------------------------------------
    # 优先查找当前目录下的字体文件，你可以把 SimHei.ttf 或 NotoSansSC.otf 放进来
    font_path = None
    possible_fonts = [
        "font.otf",          # 刚才让你下载的
        "font.ttf",          # 刚才让你下载的
        "SimHei.ttf",        # Windows 常用
        "msyh.ttc",          # Windows 微软雅黑
        "NotoSansSC-Regular.otf", # Linux 常见开源
        "/System/Library/Fonts/PingFang.ttc", # Mac
        "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf" # Linux 旧版通用
    ]
    
    for f in possible_fonts:
        if os.path.exists(f):
            font_path = f
            print(f"✅ 成功找到字体文件: {f}")
            break
            
    if not font_path:
        print("❌ 错误：未找到任何中文字体文件！")
        print("👉 请下载一个中文字体(如 font.otf)放到脚本同级目录下再运行。")
        return

    try:
        # 加载字体
        font_title = ImageFont.truetype(font_path, 80)
        font_sub = ImageFont.truetype(font_path, 40)
        font_text = ImageFont.truetype(font_path, 30)
    except Exception as e:
        print(f"❌ 字体加载失败: {e}")
        return

    # --- 4. 绘制内容 ---
    # 头部
    draw.rectangle([(0,0), (width, header_height)], fill=header_bg)
    draw.text((100, 100), "2026 快手电商", font=font_sub, fill="white")
    draw.text((100, 160), "再降本增收", font=font_title, fill="white")
    draw.text((100, 280), "全国升级 · 九大新商扶持政策", font=font_sub, fill="white")
    
    current_y = header_height + 50
    
    for p in policies:
        if p["type"] == "header":
            draw.rectangle([(0, current_y), (width, current_y+100)], fill="#FFCC00")
            # 居中计算
            text_w = draw.textlength(p["title"], font=font_sub)
            draw.text(((width - text_w)/2, current_y+20), p["title"], font=font_sub, fill="white")
            current_y += 120
            continue
            
        fill_color = blue_card if p["type"] == "blue" else orange_card
        outline_color = blue_title if p["type"] == "blue" else orange_title
        
        # 画卡片
        draw.rectangle([(50, current_y), (width-50, current_y+card_height)], fill=fill_color, outline=outline_color, width=3)
        
        # 标题条
        draw.rectangle([(50, current_y), (width-50, current_y+80)], fill=outline_color)
        draw.text((80, current_y+15), p["title"], font=font_sub, fill="white")
        
        # 内容文本
        # 简单换行处理
        content = p["content"]
        # 如果字太多可以截断或者换行，这里简单处理
        draw.text((80, current_y+150), content, font=font_text, fill=text_color)
        
        current_y += (card_height + section_gap)

    # 底部
    draw.rectangle([(0, total_height-footer_height), (width, total_height)], fill="#333333")
    footer_text = "具体规则以官方公示为准"
    ft_w = draw.textlength(footer_text, font=font_text)
    draw.text(((width-ft_w)/2, total_height-120), footer_text, font=font_text, fill="white")

    save_name = "kuaishou_policy_v2.png"
    img.save(save_name)
    print(f"🎉 长图已生成: {save_name}")

if __name__ == "__main__":
    create_long_image()
