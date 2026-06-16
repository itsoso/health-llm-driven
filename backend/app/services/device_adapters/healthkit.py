"""HealthKit 适配器 — iOS 端 HealthKit 数据汇入入口.

设计:
- 数据**不**由后端拉取,由 mobile 端从 HealthKit 聚合后 POST 进来,所以
  fetch_daily_data 抛 NotImplementedError. 这是一个"被动"适配器.
- HealthKit 是同质数据汇 (Apple Watch / RingConn / Oura / Withings App 都写它),
  按 sourceName (iOS bundle id) 区分来源. mobile 端预聚合时已确定 data_source.
- batch_save 接收前端 POST 来的 dict 列表,逐条转 NormalizedHealthData 调
  DeviceManager._save_health_data,复用现成 upsert 逻辑.

参考:
- mobile/services/appleHealth.ts 负责 HealthKit 读取、按月切片回填、POST 推送
- backend/app/api/devices.py POST /devices/healthkit/import 端点是入口
"""

from datetime import date as _date, datetime, time as _time
from typing import Any, Dict, List, Optional, Tuple
import logging

from sqlalchemy.exc import IntegrityError

from sqlalchemy.orm import Session

from .base import (
    AuthType,
    DeviceAdapter,
    DeviceType,
    NormalizedHealthData,
)

logger = logging.getLogger(__name__)


# 已知 sourceName bundle id → data_source 标签字典.
# 命中字典: 写细分 source. miss: 落 'unknown' + warning,后续看日志补字典.
_SOURCE_NAME_MAP: Dict[str, str] = {
    "com.apple.health": "apple-watch",
    "com.apple.healthkit": "apple-watch",
    "com.apple.Health": "apple-watch",
    "com.ringconn.app": "ringconn",
    "com.ringconn.RingConn": "ringconn",
    "com.ouraring.oura": "oura",
    "com.ouraring.OuraRing": "oura",
    "com.withings.wiScaleNG": "withings-app",
    "com.withings.healthmate": "withings-app",
    "com.garmin.connect.mobile": "garmin-app",
    # Garmin Connect 写 HealthKit 用显示名 "Connect"(非 bundle id、不含 "Garmin"),
    # mobile 端正则也抓不到 → 之前落 unknown(生产日志实锤)。两层 map 都补上。
    "Connect": "garmin-app",
}

# 校验白名单 — mobile 端推上来的 data_source 必须在这个集合里 (或 unknown 兜底)
_ALLOWED_DATA_SOURCES = frozenset({
    "ringconn",
    "oura",
    "apple-watch",
    "withings-app",
    "garmin-app",
    "manual",
    "unknown",
})


def map_source_name_to_data_source(source_name: Optional[str]) -> str:
    """HealthKit sourceName (bundle id) → 我们的 data_source 标签.

    miss 字典时落 'unknown' 并 warning,不抛错 (后续按日志补字典)."""
    if not source_name:
        return "unknown"
    mapped = _SOURCE_NAME_MAP.get(source_name)
    if mapped:
        return mapped
    logger.warning(f"[healthkit] unknown sourceName='{source_name}', fallback=unknown")
    return "unknown"


class HealthKitAdapter(DeviceAdapter):
    """iOS HealthKit 通用入口 — 数据由 mobile 推送,不主动拉取."""

    @property
    def device_type(self) -> DeviceType:
        return DeviceType.HEALTHKIT

    @property
    def display_name(self) -> str:
        return "Apple Health (HealthKit)"

    @property
    def auth_type(self) -> AuthType:
        # HealthKit 授权在设备本地完成 (iOS 弹窗),后端不持有 token.
        # 用 TOKEN 占位是为了让 DeviceCredential 字段够用,实际 access_token 可空.
        return AuthType.TOKEN

    async def authenticate(self, credentials: Dict[str, Any]) -> bool:
        # HealthKit 授权在 mobile 端完成,后端无法验证.约定: 只要 credential 存在就视为已授权.
        return True

    async def test_connection(self) -> Dict[str, Any]:
        return {
            "success": True,
            "message": "HealthKit 数据由 iOS App 主动推送,无需后端连通性测试",
        }

    async def fetch_daily_data(self, target_date: _date) -> Optional[NormalizedHealthData]:
        # 这是被动适配器: 数据由 mobile POST /devices/healthkit/import 推送.
        # 后端不主动从 HealthKit 拉数据 (它根本不在后端可达).
        raise NotImplementedError(
            "HealthKit 数据由 iOS App 主动推送,不支持后端主动拉取. "
            "mobile 端调 POST /api/v1/devices/healthkit/import."
        )

    @staticmethod
    def _parse_date(value: Any) -> Optional[_date]:
        if value is None:
            return None
        if isinstance(value, _date):
            return value
        if isinstance(value, str):
            try:
                return _date.fromisoformat(value[:10])
            except ValueError:
                return None
        return None

    @staticmethod
    def _parse_time(value: Any) -> Optional[_time]:
        if value is None:
            return None
        if isinstance(value, _time):
            return value
        if isinstance(value, str):
            try:
                # 接受 "HH:MM" 或 "HH:MM:SS"
                return _time.fromisoformat(value)
            except ValueError:
                try:
                    parsed = datetime.fromisoformat(value)
                    return parsed.time()
                except ValueError:
                    return None
        return None

    @staticmethod
    def _resolve_data_source(record: Dict[str, Any]) -> str:
        """从 record 解析 validated data_source — 不依赖 record_date.

        优先取 record.data_source,其次按 source_name 映射,兜底 unknown.
        独立于 _record_to_normalized,使 ECG 点事件在日聚合解析失败时仍能确定来源."""
        ds_raw = record.get("data_source")
        if ds_raw is None and record.get("source_name"):
            ds_raw = map_source_name_to_data_source(record["source_name"])
        if ds_raw not in _ALLOWED_DATA_SOURCES:
            if ds_raw is not None:
                logger.warning(f"[healthkit] data_source='{ds_raw}' 不在白名单, fallback=unknown")
            ds_raw = "unknown"
        return ds_raw

    @classmethod
    def _record_to_normalized(cls, record: Dict[str, Any]) -> Tuple[NormalizedHealthData, str]:
        """单条 record dict → NormalizedHealthData. 返回 (data, validated_data_source)."""
        record_date = cls._parse_date(record.get("record_date"))
        if record_date is None:
            raise ValueError(f"record_date 缺失或格式错误: {record.get('record_date')!r}")

        ds_raw = cls._resolve_data_source(record)

        return NormalizedHealthData(
            record_date=record_date,
            source=ds_raw,
            sleep_score=record.get("sleep_score"),
            total_sleep_minutes=record.get("total_sleep_minutes"),
            deep_sleep_minutes=record.get("deep_sleep_minutes"),
            rem_sleep_minutes=record.get("rem_sleep_minutes"),
            light_sleep_minutes=record.get("light_sleep_minutes"),
            awake_minutes=record.get("awake_minutes"),
            sleep_start_time=cls._parse_time(record.get("sleep_start_time")),
            sleep_end_time=cls._parse_time(record.get("sleep_end_time")),
            resting_heart_rate=record.get("resting_heart_rate"),
            avg_heart_rate=record.get("avg_heart_rate"),
            max_heart_rate=record.get("max_heart_rate"),
            min_heart_rate=record.get("min_heart_rate"),
            hrv=record.get("hrv"),
            hrv_status=record.get("hrv_status"),
            steps=record.get("steps"),
            distance_meters=record.get("distance_meters"),
            floors_climbed=record.get("floors_climbed"),
            active_minutes=record.get("active_minutes"),
            calories_total=record.get("calories_total"),
            calories_active=record.get("calories_active"),
            stress_level=record.get("stress_level"),
            body_battery_high=record.get("body_battery_high"),
            body_battery_low=record.get("body_battery_low"),
            spo2_avg=record.get("spo2_avg"),
            spo2_min=record.get("spo2_min"),
            respiration_rate_avg=record.get("respiration_rate_avg"),
            respiration_rate_min=record.get("respiration_rate_min"),
            respiration_rate_max=record.get("respiration_rate_max"),
            body_temp_deviation_c=record.get("body_temp_deviation_c"),
            raw_data=record.get("raw_data") or {},
        ), ds_raw

    @staticmethod
    def _parse_datetime(value: Any) -> Optional[datetime]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return None
        return None

    @classmethod
    def _save_ecg(cls, db: Session, user_id: int, record: Dict[str, Any], data_source: str) -> bool:
        """落库一条 ECG 观测 (点事件, 独立 ecg_observations 表). 返回是否写入.

        仅当 ecg_classification 存在时落库. (user_id, recorded_at) 唯一 → 重复上送幂等:
        命中已存在则更新分类/计数, 否则插入. raw_data 留审计."""
        classification = record.get("ecg_classification")
        if not classification:
            return False

        from app.models.ecg_observation import EcgObservation

        recorded_at = cls._parse_datetime(record.get("ecg_recorded_at"))
        afib_count = record.get("afib_event_count") or 0
        try:
            afib_count = int(afib_count)
        except (TypeError, ValueError):
            afib_count = 0

        existing = None
        if recorded_at is not None:
            existing = (
                db.query(EcgObservation)
                .filter(
                    EcgObservation.user_id == user_id,
                    EcgObservation.recorded_at == recorded_at,
                )
                .first()
            )

        if existing:
            existing.classification = str(classification)
            existing.afib_event_count = afib_count
            existing.data_source = data_source
            existing.raw_data = record.get("raw_data") or existing.raw_data
        else:
            db.add(EcgObservation(
                user_id=user_id,
                classification=str(classification),
                recorded_at=recorded_at,
                afib_event_count=afib_count,
                data_source=data_source,
                raw_data=record.get("raw_data") or None,
            ))
        try:
            db.commit()
        except IntegrityError:
            # 并发/重复上送撞唯一约束 — 回滚视为幂等成功, 不抛给整批
            db.rollback()
        return True

    @staticmethod
    def _coerce_int(value: Any) -> Optional[int]:
        """容错取整: float/数字字符串 → int, 坏值 → None (丢弃不崩)。"""
        if value is None:
            return None
        if isinstance(value, bool):  # bool 是 int 子类, 显式拒绝
            return None
        try:
            return int(round(float(value)))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _coerce_float(value: Any) -> Optional[float]:
        """容错转 float: 坏值 → None (丢弃不崩)。"""
        if value is None:
            return None
        if isinstance(value, bool):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _save_blood_pressure(cls, db: Session, user_id: int, reading: Dict[str, Any]) -> bool:
        """落库一条血压点事件 (blood_pressure_records 表). 返回是否写入.

        血压是点事件 (一天多次), 与 ECG 同范式: 按 (user_id, measured_at) 去重幂等。
        - systolic/diastolic 容错取整, 任一缺失/坏值 → 整条丢弃返回 False (不写半截记录)。
        - measured_at 缺失/不可解析 → 无去重锚点, 丢弃返回 False (点事件必须带测量时刻)。
        - record_date 从 measured_at 推导。
        - 命中已存在 (同 user+measured_at) 则跳过 (幂等), 不覆盖。
        - IntegrityError (并发撞唯一约束) 回滚视为幂等成功。
        """
        systolic = cls._coerce_int(reading.get("systolic"))
        diastolic = cls._coerce_int(reading.get("diastolic"))
        if systolic is None or diastolic is None:
            return False

        measured_at = cls._parse_datetime(reading.get("measured_at"))
        if measured_at is None:
            return False

        from app.models.blood_pressure import BloodPressureRecord

        existing = (
            db.query(BloodPressureRecord)
            .filter(
                BloodPressureRecord.user_id == user_id,
                BloodPressureRecord.measured_at == measured_at,
            )
            .first()
        )
        if existing:
            # 已存在同测量时刻记录 → 幂等跳过, 不覆盖 (重复上送不增行)。
            return False

        source = reading.get("source")
        notes = f"HealthKit 自动同步 ({source})" if source else "HealthKit 自动同步"
        db.add(BloodPressureRecord(
            user_id=user_id,
            record_date=measured_at.date(),
            measured_at=measured_at,
            systolic=systolic,
            diastolic=diastolic,
            notes=notes,
        ))
        try:
            db.commit()
        except IntegrityError:
            # 并发/重复上送撞唯一约束 — 回滚视为幂等成功, 不抛给整批
            db.rollback()
            return False
        return True

    @classmethod
    def _save_body_composition(cls, db: Session, user_id: int, record: Dict[str, Any], data_source: str) -> bool:
        """落库体重+体脂到 weight_records 表 (随体重, 按天 upsert). 返回是否写入.

        - 仅当存在 weight_kg 时落库 (weight 列 NOT NULL, body_fat 必须随体重)。
          只有 body_fat 没 weight → 无载体, 返回 False。
        - body_fat_percentage 容错 float, 缺失则不写该列。
        - 按 (user_id, record_date) upsert (与 /weight/records 端点同语义), 重复幂等。
        """
        weight = cls._coerce_float(record.get("weight_kg"))
        if weight is None:
            return False

        record_date = cls._parse_date(record.get("record_date"))
        if record_date is None:
            return False

        body_fat = cls._coerce_float(record.get("body_fat_percentage"))

        from app.models.weight import WeightRecord

        existing = (
            db.query(WeightRecord)
            .filter(
                WeightRecord.user_id == user_id,
                WeightRecord.record_date == record_date,
            )
            .first()
        )
        if existing:
            existing.weight = weight
            if body_fat is not None:
                existing.body_fat_percentage = body_fat
            if not existing.source:
                existing.source = data_source
        else:
            db.add(WeightRecord(
                user_id=user_id,
                record_date=record_date,
                weight=weight,
                body_fat_percentage=body_fat,
                source=data_source,
                notes="HealthKit 自动同步",
            ))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
        return True

    @classmethod
    def batch_save(
        cls,
        db: Session,
        user_id: int,
        records: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """逐条独立 try/except 写入 garmin_data,一条坏数据不让整批 fail.

        ECG 是点事件,语义上**不依赖**日聚合写入成功,因此与日聚合并行各自独立
        try/except:即使 _record_to_normalized(日聚合)因 record_date 缺失抛错,
        本条若带 ecg_classification 仍尝试落 ECG。ECG 丢弃/落库失败走**可区分**的
        "ECG dropped" 错误项(`kind: "ecg"`),不混进通用 record error,让调用方感知。

        血压 (blood_pressure_readings) 同理是**点事件** (一天多次): 与日聚合并行各自
        独立 try, 逐条按 (user_id, measured_at) 去重幂等落 blood_pressure_records,
        失败走可区分 "BP dropped" 错误项 (`kind: "blood_pressure"`)。
        体脂 (body_fat_percentage) 随体重 (weight_kg) 落 weight_records, 也独立 try
        (`kind: "body_composition"`)。各源失败互不影响, 不静默吞。

        返回:
          {
            "imported_count": int,
            "ecg_imported_count": int,
            "blood_pressure_imported_count": int,
            "source_breakdown": {"apple-watch": 12, "ringconn": 5, ...},
            "errors": [
              {"index": int,
               "kind": "daily"|"ecg"|"blood_pressure"|"body_composition",
               "record_date": str|None, "error": str},
              ...
            ]
          }
        """
        from .manager import DeviceManager

        imported = 0
        ecg_imported = 0
        bp_imported = 0
        breakdown: Dict[str, int] = {}
        errors: List[Dict[str, Any]] = []

        for idx, record in enumerate(records):
            # ── 日聚合写入 (独立 try) ────────────────────────────────────────
            try:
                normalized, ds = cls._record_to_normalized(record)
                DeviceManager._save_health_data(db, user_id, normalized)
                imported += 1
                breakdown[ds] = breakdown.get(ds, 0) + 1
            except Exception as e:
                logger.warning(
                    f"[healthkit] batch_save idx={idx} record_date={record.get('record_date')!r} "
                    f"failed: {type(e).__name__}: {e}"
                )
                errors.append({
                    "index": idx,
                    "kind": "daily",
                    "record_date": str(record.get("record_date")) if record.get("record_date") else None,
                    "error": f"{type(e).__name__}: {e}",
                })
                # _save_health_data 内部 db.commit() 失败时由调用方负责 rollback;
                # 这里独立 try 仅捕获,后续逻辑继续。
                try:
                    db.rollback()
                except Exception:
                    pass

            # ── ECG 点事件写入 (独立 try, 与日聚合并行) ──────────────────────
            # 即使日聚合失败也尝试落 ECG: ECG 是点事件, 不依赖日聚合成功。
            # data_source 独立解析 (不经 _record_to_normalized, 后者可能已抛错)。
            if record.get("ecg_classification"):
                try:
                    ds_ecg = cls._resolve_data_source(record)
                    if cls._save_ecg(db, user_id, record, ds_ecg):
                        ecg_imported += 1
                except Exception as ecg_err:  # noqa: BLE001
                    # 可区分日志: 明确 "ECG dropped", 不混进通用 record error。
                    logger.error(
                        f"[healthkit] ECG dropped idx={idx} "
                        f"ecg_recorded_at={record.get('ecg_recorded_at')!r} "
                        f"classification={record.get('ecg_classification')!r}: "
                        f"{type(ecg_err).__name__}: {ecg_err}"
                    )
                    errors.append({
                        "index": idx,
                        "kind": "ecg",
                        "record_date": str(record.get("ecg_recorded_at")) if record.get("ecg_recorded_at") else None,
                        "error": f"ECG dropped: {type(ecg_err).__name__}: {ecg_err}",
                    })
                    try:
                        db.rollback()
                    except Exception:
                        pass

            # ── 血压点事件写入 (独立 try, 与日聚合并行) ──────────────────────
            # 血压一天多次、是点事件, 不依赖日聚合成功。每条 reading 各自去重幂等落库。
            bp_readings = record.get("blood_pressure_readings")
            if bp_readings:
                for bp_idx, reading in enumerate(bp_readings):
                    try:
                        if cls._save_blood_pressure(db, user_id, reading):
                            bp_imported += 1
                    except Exception as bp_err:  # noqa: BLE001
                        logger.error(
                            f"[healthkit] BP dropped idx={idx} reading={bp_idx} "
                            f"measured_at={reading.get('measured_at')!r}: "
                            f"{type(bp_err).__name__}: {bp_err}"
                        )
                        errors.append({
                            "index": idx,
                            "kind": "blood_pressure",
                            "record_date": str(reading.get("measured_at")) if reading.get("measured_at") else None,
                            "error": f"BP dropped: {type(bp_err).__name__}: {bp_err}",
                        })
                        try:
                            db.rollback()
                        except Exception:
                            pass

            # ── 体脂随体重写入 (独立 try, 与日聚合并行) ──────────────────────
            # body_fat_percentage 随 weight_kg 落 weight_records。只有 body_fat 没
            # weight → _save_body_composition 返回 False (无 NOT NULL 载体), 不报错。
            if record.get("weight_kg") is not None or record.get("body_fat_percentage") is not None:
                try:
                    ds_bc = cls._resolve_data_source(record)
                    cls._save_body_composition(db, user_id, record, ds_bc)
                except Exception as bc_err:  # noqa: BLE001
                    logger.error(
                        f"[healthkit] body_composition dropped idx={idx} "
                        f"record_date={record.get('record_date')!r}: "
                        f"{type(bc_err).__name__}: {bc_err}"
                    )
                    errors.append({
                        "index": idx,
                        "kind": "body_composition",
                        "record_date": str(record.get("record_date")) if record.get("record_date") else None,
                        "error": f"body_composition dropped: {type(bc_err).__name__}: {bc_err}",
                    })
                    try:
                        db.rollback()
                    except Exception:
                        pass

        return {
            "imported_count": imported,
            "ecg_imported_count": ecg_imported,
            "blood_pressure_imported_count": bp_imported,
            "source_breakdown": breakdown,
            "errors": errors,
        }
