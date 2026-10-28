import Image from 'next/image';
import xiaoqihouIcon from '@/assets/xiaoqihou-icon.png';

export const BRAND_NAME = '小气候';

interface BrandIconProps {
  size?: number;
  className?: string;
  priority?: boolean;
}

export function BrandIcon({ size = 32, className, priority = false }: BrandIconProps) {
  return (
    <Image
      src={xiaoqihouIcon}
      alt=""
      width={size}
      height={size}
      className={className}
      priority={priority}
    />
  );
}
