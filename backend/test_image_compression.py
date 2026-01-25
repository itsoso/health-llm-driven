"""
测试图片压缩功能

运行前需要安装: pip install Pillow
"""
import io
from PIL import Image

def create_test_image(size=(2000, 2000), color=(255, 0, 0)):
    """创建测试图片"""
    img = Image.new('RGB', size, color)
    output = io.BytesIO()
    img.save(output, format='JPEG', quality=95)
    return output.getvalue()

def test_compression():
    """测试压缩功能"""
    print("=" * 60)
    print("图片压缩功能测试")
    print("=" * 60)
    
    try:
        from app.utils.image_compression import compress_image, should_compress, get_image_info
        
        # 创建测试图片
        print("\n1. 创建测试图片 (2000x2000, JPEG)...")
        test_data = create_test_image()
        original_size = len(test_data)
        print(f"   原始大小: {original_size / 1024:.1f}KB")
        
        # 获取图片信息
        print("\n2. 获取图片信息...")
        info = get_image_info(test_data)
        print(f"   格式: {info.get('format')}")
        print(f"   尺寸: {info.get('width')}x{info.get('height')}")
        print(f"   模式: {info.get('mode')}")
        
        # 判断是否需要压缩
        print("\n3. 判断是否需要压缩...")
        needs_compression = should_compress(test_data, threshold_kb=500)
        print(f"   需要压缩: {needs_compression}")
        
        # 压缩图片
        print("\n4. 压缩图片...")
        compressed_data, format_type = compress_image(
            test_data,
            max_width=1920,
            max_height=1920,
            quality=85
        )
        compressed_size = len(compressed_data)
        compression_ratio = (1 - compressed_size / original_size) * 100
        
        print(f"   压缩后大小: {compressed_size / 1024:.1f}KB")
        print(f"   压缩率: {compression_ratio:.1f}%")
        print(f"   输出格式: {format_type}")
        
        # 验证压缩后的图片
        print("\n5. 验证压缩后的图片...")
        compressed_info = get_image_info(compressed_data)
        print(f"   格式: {compressed_info.get('format')}")
        print(f"   尺寸: {compressed_info.get('width')}x{compressed_info.get('height')}")
        
        print("\n" + "=" * 60)
        print("✅ 测试通过!")
        print("=" * 60)
        
        return True
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_compression()
