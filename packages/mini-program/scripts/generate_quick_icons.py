#!/usr/bin/env python3
"""
生成快捷功能图标 - 线条风格
"""
from PIL import Image, ImageDraw
import os
import math

# 图标尺寸
SIZE = 120

# 颜色定义
COLORS = {
    'blue': (59, 130, 246),      # #3B82F6
    'yellow': (234, 179, 8),     # #EAB308
    'orange': (249, 115, 22),    # #F97316
    'purple': (139, 92, 246),    # #8B5CF6
}

def create_icon(icon_type, color):
    """创建图标"""
    scale = 3
    img = Image.new('RGBA', (SIZE * scale, SIZE * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    center = (SIZE * scale) // 2
    lw = 8 * scale  # 线条粗细

    if icon_type == 'checkin':
        # 每日打卡 - 日历/剪贴板图标
        # 主体矩形
        left = center - 28 * scale
        right = center + 28 * scale
        top = center - 24 * scale
        bottom = center + 30 * scale
        
        # 圆角矩形主体
        draw.rounded_rectangle([left, top, right, bottom], radius=6*scale, outline=color, width=lw)
        
        # 顶部两个小夹子
        clip_y = top - 4 * scale
        clip_h = 12 * scale
        draw.rounded_rectangle([center - 16*scale, clip_y, center - 8*scale, top + 6*scale], 
                               radius=3*scale, outline=color, width=lw)
        draw.rounded_rectangle([center + 8*scale, clip_y, center + 16*scale, top + 6*scale], 
                               radius=3*scale, outline=color, width=lw)
        
        # 打勾
        check_cx = center
        check_cy = center + 8 * scale
        draw.line([(check_cx - 14*scale, check_cy), (check_cx - 4*scale, check_cy + 10*scale)], 
                  fill=color, width=lw, joint='curve')
        draw.line([(check_cx - 4*scale, check_cy + 10*scale), (check_cx + 16*scale, check_cy - 10*scale)], 
                  fill=color, width=lw, joint='curve')

    elif icon_type == 'diet':
        # 饮食记录 - 刀叉图标
        fork_x = center - 14 * scale
        knife_x = center + 14 * scale
        top_y = center - 32 * scale
        bottom_y = center + 32 * scale
        
        # 叉子
        # 叉子柄
        draw.line([(fork_x, center), (fork_x, bottom_y)], fill=color, width=lw)
        # 叉子头部三个齿
        draw.line([(fork_x - 10*scale, top_y), (fork_x - 10*scale, center - 8*scale)], fill=color, width=lw-2*scale)
        draw.line([(fork_x, top_y), (fork_x, center - 8*scale)], fill=color, width=lw-2*scale)
        draw.line([(fork_x + 10*scale, top_y), (fork_x + 10*scale, center - 8*scale)], fill=color, width=lw-2*scale)
        # 叉子头部连接
        draw.arc([fork_x - 12*scale, center - 14*scale, fork_x + 12*scale, center + 4*scale], 
                 start=0, end=180, fill=color, width=lw)
        
        # 刀子
        # 刀柄
        draw.line([(knife_x, center + 4*scale), (knife_x, bottom_y)], fill=color, width=lw)
        # 刀刃 - 椭圆形
        draw.ellipse([knife_x - 8*scale, top_y, knife_x + 8*scale, center + 8*scale], outline=color, width=lw)

    elif icon_type == 'workout':
        # 运动训练 - 跑步人图标
        head_r = 10 * scale
        head_cx = center + 4 * scale
        head_cy = center - 22 * scale
        
        # 头
        draw.ellipse([head_cx - head_r, head_cy - head_r, head_cx + head_r, head_cy + head_r], 
                     outline=color, width=lw)
        
        # 身体 - 倾斜
        body_top = head_cy + head_r + 2*scale
        body_bottom_x = center - 6*scale
        body_bottom_y = center + 8*scale
        draw.line([(head_cx, body_top), (body_bottom_x, body_bottom_y)], fill=color, width=lw)
        
        # 手臂 - 向后摆
        arm_start = (head_cx - 2*scale, body_top + 8*scale)
        draw.line([arm_start, (center - 24*scale, center - 8*scale)], fill=color, width=lw)
        draw.line([arm_start, (center + 20*scale, center + 2*scale)], fill=color, width=lw)
        
        # 腿 - 跑步姿势
        leg_start = (body_bottom_x, body_bottom_y)
        # 前腿
        draw.line([leg_start, (center + 16*scale, center + 28*scale)], fill=color, width=lw)
        # 后腿
        draw.line([leg_start, (center - 28*scale, center + 20*scale)], fill=color, width=lw)

    elif icon_type == 'health':
        # 健康数据 - 心电图/脉搏图标
        # 矩形框
        left = center - 30 * scale
        right = center + 30 * scale
        top = center - 22 * scale
        bottom = center + 22 * scale
        
        draw.rounded_rectangle([left, top, right, bottom], radius=6*scale, outline=color, width=lw)
        
        # 心电图波形
        wave_y = center
        points = [
            (left + 8*scale, wave_y),
            (center - 18*scale, wave_y),
            (center - 12*scale, wave_y - 14*scale),
            (center - 4*scale, wave_y + 10*scale),
            (center + 4*scale, wave_y - 18*scale),
            (center + 12*scale, wave_y + 8*scale),
            (center + 18*scale, wave_y),
            (right - 8*scale, wave_y),
        ]
        draw.line(points, fill=color, width=lw-2*scale, joint='curve')

    # 缩放到目标尺寸
    img = img.resize((SIZE, SIZE), Image.LANCZOS)
    return img

def main():
    output_dir = os.path.join(os.path.dirname(__file__), '../src/assets/icons')
    os.makedirs(output_dir, exist_ok=True)

    print("生成快捷功能图标...")

    icons = {
        'checkin': ('quick-checkin', 'blue', '每日打卡'),
        'diet': ('quick-diet', 'yellow', '饮食记录'),
        'workout': ('quick-workout', 'orange', '运动训练'),
        'health': ('quick-health', 'purple', '健康数据'),
    }

    for icon_type, (filename, color_name, label) in icons.items():
        print(f"\n生成 {label} 图标...")
        color = COLORS[color_name]
        icon = create_icon(icon_type, color)
        filepath = os.path.join(output_dir, f'{filename}.png')
        icon.save(filepath)
        print(f"  ✓ {filename}.png")

    print("\n完成！所有快捷功能图标已生成。")
    print(f"图标尺寸: {SIZE}x{SIZE}px")

if __name__ == '__main__':
    main()
