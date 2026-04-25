#!/usr/bin/env python3
"""
生成小程序TabBar图标 - 终极醒目版
"""
from PIL import Image, ImageDraw
import os
import math

# 图标尺寸（小程序要求81x81）
SIZE = 81

# 颜色定义
COLOR_GRAY = (140, 140, 150)  # 中性灰
COLOR_PRIMARY = (88, 80, 236)  # #5850ec 鲜艳的靛蓝

# 线条粗细 - 加粗！
LINE_WIDTH = 6


def create_icon(icon_type, color, filled=False):
    """创建图标"""
    # 创建透明背景（3x 分辨率抗锯齿）
    scale = 3
    img = Image.new('RGBA', (SIZE * scale, SIZE * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    center = (SIZE * scale) // 2
    lw = LINE_WIDTH * scale

    # 基础尺寸 - 进一步加大，占满画布
    # 81px * 3 = 243px, 留边距约 15px * 3 = 45px
    # 图标大小约 66px (在81px画布上)
    base_size = 66 * scale // 2

    if icon_type == 'home':
        # 首页：饱满的房子
        house_w = base_size * 1.5
        house_h = base_size * 1.1
        roof_h = base_size * 0.8

        # 屋顶顶点
        roof_top = center - base_size + 4*scale
        # 屋檐宽度
        eave_w = house_w + 12*scale

        # 房子主体
        body_top = roof_top + roof_h
        body_bottom = center + base_size - 4*scale

        if filled:
            # 填充屋顶
            draw.polygon([
                (center, roof_top),
                (center - eave_w//2, body_top),
                (center + eave_w//2, body_top)
            ], fill=color)
            # 填充主体
            draw.rectangle(
                [center - house_w//2, body_top, center + house_w//2, body_bottom],
                fill=color
            )
            # 门（白色）
            door_w = house_w * 0.35
            door_h = (body_bottom - body_top) * 0.6
            draw.rounded_rectangle(
                [center - door_w//2, body_bottom - door_h, center + door_w//2, body_bottom],
                radius=4*scale,
                fill=(255, 255, 255, 255)
            )
        else:
            # 线条屋顶
            draw.line([(center, roof_top), (center - eave_w//2, body_top)], fill=color, width=lw, joint='curve')
            draw.line([(center, roof_top), (center + eave_w//2, body_top)], fill=color, width=lw, joint='curve')
            # 线条主体
            # 左右墙
            draw.line([(center - house_w//2 + lw//2, body_top), (center - house_w//2 + lw//2, body_bottom)], fill=color, width=lw)
            draw.line([(center + house_w//2 - lw//2, body_top), (center + house_w//2 - lw//2, body_bottom)], fill=color, width=lw)
            # 地板
            draw.line([(center - house_w//2, body_bottom), (center + house_w//2, body_bottom)], fill=color, width=lw)
            # 门
            door_w = house_w * 0.35
            door_h = (body_bottom - body_top) * 0.6
            draw.rounded_rectangle(
                [center - door_w//2, body_bottom - door_h, center + door_w//2, body_bottom],
                radius=4*scale,
                outline=color,
                width=lw
            )

    elif icon_type == 'ai-assistant':
        # 建议：闪电/魔法棒（更醒目）
        # 绘制一个饱满的四角星
        star_r = base_size * 0.95

        points = []
        for i in range(4):
            angle = i * 90
            rad = math.radians(angle)
            # 外点
            points.append((center + math.cos(rad) * star_r, center + math.sin(rad) * star_r))
            # 内点 (更加向内收缩，形成尖锐感)
            rad_in = math.radians(angle + 45)
            inner_r = star_r * 0.35
            points.append((center + math.cos(rad_in) * inner_r, center + math.sin(rad_in) * inner_r))

        if filled:
            draw.polygon(points, fill=color)
            # 旁边加个小点缀
            dot_r = 6*scale
            dot_x = center + star_r * 0.6
            dot_y = center - star_r * 0.6
            draw.ellipse([dot_x-dot_r, dot_y-dot_r, dot_x+dot_r, dot_y+dot_r], fill=color)
        else:
            # 闭合线条
            points.append(points[0])
            draw.line(points, fill=color, width=lw, joint='curve')
            # 旁边加个小圈
            dot_r = 5*scale
            dot_x = center + star_r * 0.6
            dot_y = center - star_r * 0.6
            draw.ellipse([dot_x-dot_r, dot_y-dot_r, dot_x+dot_r, dot_y+dot_r], outline=color, width=lw)

    elif icon_type == 'checkin':
        # 打卡：极简大对勾（去掉外框，更直接）
        # 或者保留圆框但加大对勾

        # 这次尝试：实心圆/空心圆 + 超大对勾
        radius = base_size * 0.9

        if filled:
            # 实心圆
            draw.ellipse(
                [center - radius, center - radius, center + radius, center + radius],
                fill=color
            )
            # 白色对勾
            check_w = lw * 1.5 # 对勾更粗
            draw.line([
                (center - 12*scale, center + 2*scale),
                (center - 2*scale, center + 14*scale),
                (center + 16*scale, center - 8*scale)
            ], fill=(255, 255, 255, 255), width=int(check_w), joint='curve')
        else:
            # 空心圆
            draw.ellipse(
                [center - radius, center - radius, center + radius, center + radius],
                outline=color,
                width=lw
            )
            # 内部对勾
            draw.line([
                (center - 12*scale, center + 2*scale),
                (center - 2*scale, center + 14*scale),
                (center + 16*scale, center - 8*scale)
            ], fill=color, width=lw, joint='curve')

    elif icon_type == 'user':
        # 我的：大头像
        head_r = base_size * 0.45
        head_y = center - base_size * 0.4

        body_w = base_size * 1.6
        body_h = base_size * 0.7
        body_y = center + base_size * 0.9

        if filled:
            # 头部
            draw.ellipse(
                [center - head_r, head_y - head_r, center + head_r, head_y + head_r],
                fill=color
            )
            # 身体 (半椭圆)
            draw.chord(
                [center - body_w//2, body_y - body_h*2,
                 center + body_w//2, body_y],
                start=0, end=180,
                fill=color
            )
        else:
            # 头部
            draw.ellipse(
                [center - head_r, head_y - head_r, center + head_r, head_y + head_r],
                outline=color,
                width=lw
            )
            # 身体
            draw.arc(
                [center - body_w//2, body_y - body_h*2,
                 center + body_w//2, body_y],
                start=0, end=180,
                fill=color, width=lw
            )
            # 底边封口
            draw.line(
                [(center - body_w//2, body_y), (center + body_w//2, body_y)],
                fill=color, width=lw
            )

    # 缩小到目标尺寸（抗锯齿）
    img = img.resize((SIZE, SIZE), Image.LANCZOS)

    return img


def main():
    """主函数"""
    # 输出目录
    output_dir = 'src/assets/icons'
    os.makedirs(output_dir, exist_ok=True)

    # 定义所有需要生成的图标
    icons = [
        ('home', '首页'),
        ('ai-assistant', '建议'),
        ('checkin', '打卡'),
        ('user', '我的'),
    ]

    print('生成TabBar图标（终极醒目版）...\n')

    for icon_type, icon_name in icons:
        print(f'生成{icon_name}图标...')

        # 未选中状态（灰色，线条风格）
        icon_gray = create_icon(icon_type, COLOR_GRAY, filled=False)
        icon_gray.save(os.path.join(output_dir, f'{icon_type}.png'), 'PNG')
        print(f'  ✓ {icon_type}.png (线条)')

        # 选中状态（主题色，填充风格）
        icon_active = create_icon(icon_type, COLOR_PRIMARY, filled=True)
        icon_active.save(os.path.join(output_dir, f'{icon_type}-active.png'), 'PNG')
        print(f'  ✓ {icon_type}-active.png (填充)')
        print()

    print('完成！所有图标已生成。')
    print(f'图标尺寸: {SIZE}x{SIZE}px')
    print(f'未选中颜色: RGB{COLOR_GRAY}')
    print(f'选中颜色: RGB{COLOR_PRIMARY}')

if __name__ == '__main__':
    main()
