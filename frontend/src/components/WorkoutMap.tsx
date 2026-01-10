'use client';

import { useEffect, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

// 修复 Leaflet 默认图标问题
delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
});

interface WorkoutMapProps {
  routeData?: Array<{ lat: number; lng: number; elevation?: number }>;
  startPoint?: { lat: number; lng: number };
  endPoint?: { lat: number; lng: number };
  className?: string;
}

export default function WorkoutMap({ routeData, startPoint, endPoint, className = '' }: WorkoutMapProps) {
  const mapRef = useRef<L.Map | null>(null);
  const mapContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!mapContainerRef.current) return;

    // 初始化地图
    if (!mapRef.current) {
      // 如果有路线数据，计算中心点和边界
      let center: [number, number] = [39.9042, 116.4074]; // 默认北京
      let bounds: L.LatLngBounds | null = null;

      if (routeData && routeData.length > 0) {
        const lats = routeData.map(p => p.lat);
        const lngs = routeData.map(p => p.lng);
        const minLat = Math.min(...lats);
        const maxLat = Math.max(...lats);
        const minLng = Math.min(...lngs);
        const maxLng = Math.max(...lngs);
        
        center = [(minLat + maxLat) / 2, (minLng + maxLng) / 2];
        bounds = L.latLngBounds(
          [minLat, minLng],
          [maxLat, maxLng]
        );
      } else if (startPoint) {
        center = [startPoint.lat, startPoint.lng];
      }

      mapRef.current = L.map(mapContainerRef.current, {
        center,
        zoom: bounds ? undefined : 13,
        zoomControl: true,
      });

      // 添加 OpenStreetMap 瓦片图层
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors',
        maxZoom: 19,
      }).addTo(mapRef.current);

      // 如果有边界，设置地图视图
      if (bounds) {
        mapRef.current.fitBounds(bounds, { padding: [20, 20] });
      }
    }

    const map = mapRef.current;

    // 清除之前的路线和标记
    map.eachLayer((layer) => {
      if (layer instanceof L.Polyline || layer instanceof L.Marker) {
        map.removeLayer(layer);
      }
    });

    // 绘制路线
    if (routeData && routeData.length > 0) {
      const routePoints = routeData.map(p => [p.lat, p.lng] as [number, number]);
      
      // 创建路线折线
      const polyline = L.polyline(routePoints, {
        color: '#3b82f6',
        weight: 4,
        opacity: 0.8,
      }).addTo(map);

      // 添加起点标记
      if (routeData[0]) {
        L.marker([routeData[0].lat, routeData[0].lng], {
          icon: L.icon({
            iconUrl: 'data:image/svg+xml;base64,' + btoa(`
              <svg xmlns="http://www.w3.org/2000/svg" width="25" height="41" viewBox="0 0 25 41">
                <path fill="#22c55e" d="M12.5 0C5.6 0 0 5.6 0 12.5c0 8.8 12.5 28.5 12.5 28.5S25 21.3 25 12.5C25 5.6 19.4 0 12.5 0z"/>
                <circle fill="#fff" cx="12.5" cy="12.5" r="6"/>
              </svg>
            `),
            iconSize: [25, 41],
            iconAnchor: [12, 41],
          }),
        }).addTo(map).bindPopup('起点');
      }

      // 添加终点标记
      if (routeData.length > 1) {
        const lastPoint = routeData[routeData.length - 1];
        L.marker([lastPoint.lat, lastPoint.lng], {
          icon: L.icon({
            iconUrl: 'data:image/svg+xml;base64,' + btoa(`
              <svg xmlns="http://www.w3.org/2000/svg" width="25" height="41" viewBox="0 0 25 41">
                <path fill="#ef4444" d="M12.5 0C5.6 0 0 5.6 0 12.5c0 8.8 12.5 28.5 12.5 28.5S25 21.3 25 12.5C25 5.6 19.4 0 12.5 0z"/>
                <circle fill="#fff" cx="12.5" cy="12.5" r="6"/>
              </svg>
            `),
            iconSize: [25, 41],
            iconAnchor: [12, 41],
          }),
        }).addTo(map).bindPopup('终点');
      }
    } else if (startPoint) {
      // 只有起点，显示单个标记
      L.marker([startPoint.lat, startPoint.lng]).addTo(map).bindPopup('起点');
      if (endPoint) {
        L.marker([endPoint.lat, endPoint.lng]).addTo(map).bindPopup('终点');
      }
    }

    // 清理函数
    return () => {
      if (mapRef.current) {
        mapRef.current.remove();
        mapRef.current = null;
      }
    };
  }, [routeData, startPoint, endPoint]);

  return (
    <div 
      ref={mapContainerRef} 
      className={`w-full h-full min-h-[400px] rounded-lg overflow-hidden ${className}`}
      style={{ zIndex: 0 }}
    />
  );
}
