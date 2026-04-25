"""Garmin Connect 数据 getter 方法 (Mixin).

从 garmin_connect.py 抽出. 18 个 get_*_data 方法 + 1 个 get_all_daily_data
聚合方法都在这里, 都是 self.client.* 的瘦封装 + 失败兜底.

GarminConnectService 继承本 Mixin 即获得所有 get_* 能力.

使用 Mixin 而非 free-function 是因为这些方法依赖:
- self.client          (garminconnect 库实例)
- self._log_prefix()   (用户级日志前缀)
- self._ensure_authenticated()  (token 续期)

如果改成 free function, 需要把 3 个东西都作为参数传进去, 反而更啰嗦.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List, Optional

from app.services.data_collection.garmin_errors import GarminAuthenticationError

logger = logging.getLogger(__name__)


class GarminGettersMixin:
    """所有 Garmin 单条数据 getter 方法 + 聚合 get_all_daily_data.

    必须由有 self.client / self._log_prefix() / self._ensure_authenticated()
    的子类继承使用. 不要直接实例化.
    """

    def get_user_summary(self, target_date: date) -> Optional[Dict[str, Any]]:
        """
        获取指定日期的每日摘要数据

        Args:
            target_date: 目标日期

        Returns:
            包含所有健康数据的字典，如果失败返回None
        """
        prefix = self._log_prefix()
        try:
            self._ensure_authenticated()

            # 使用get_user_summary获取每日摘要（garminconnect库的实际方法名）
            summary = self.client.get_user_summary(target_date.isoformat())

            if summary:
                logger.info(f"{prefix} 成功获取 {target_date} 的Garmin数据")
                return summary
            else:
                logger.warning(f"{prefix} 未找到 {target_date} 的数据")
                return None

        except GarminAuthenticationError:
            raise
        except Exception as e:
            logger.error(f"{prefix} 获取Garmin数据失败: {str(e)}")
            return None

    def get_sleep_data(self, target_date: date) -> Optional[Dict[str, Any]]:
        """
        获取睡眠数据

        Args:
            target_date: 目标日期

        Returns:
            睡眠数据字典
        """
        prefix = self._log_prefix()
        try:
            self._ensure_authenticated()
            sleep_data = self.client.get_sleep_data(target_date.isoformat())
            if sleep_data:
                logger.info(f"{prefix} 获取 {target_date} 的睡眠数据成功，类型: {type(sleep_data).__name__}")
            else:
                logger.warning(f"{prefix} 获取 {target_date} 的睡眠数据为空")
            return sleep_data
        except GarminAuthenticationError:
            raise
        except Exception as e:
            logger.error(f"{prefix} 获取睡眠数据失败: {str(e)}")
            return None

    def get_heart_rates(self, target_date: date) -> Optional[Dict[str, Any]]:
        """
        获取心率数据

        Args:
            target_date: 目标日期

        Returns:
            心率数据字典
        """
        prefix = self._log_prefix()
        try:
            self._ensure_authenticated()
            hr_data = self.client.get_heart_rates(target_date.isoformat())
            return hr_data
        except GarminAuthenticationError:
            # 认证错误需要传递出去
            raise
        except Exception as e:
            logger.error(f"{prefix} 获取心率数据失败: {str(e)}")
            return None

    def get_body_battery(self, target_date: date) -> Optional[Dict[str, Any]]:
        """
        获取身体电量数据

        Args:
            target_date: 目标日期

        Returns:
            身体电量数据字典
        """
        prefix = self._log_prefix()
        try:
            self._ensure_authenticated()
            battery_data = self.client.get_body_battery(target_date.isoformat())
            return battery_data
        except GarminAuthenticationError:
            raise
        except Exception as e:
            logger.error(f"{prefix} 获取身体电量数据失败: {str(e)}")
            return None

    def get_spo2_data(self, target_date: date) -> Optional[Dict[str, Any]]:
        """
        获取血氧饱和度数据

        Args:
            target_date: 目标日期

        Returns:
            血氧数据字典
        """
        prefix = self._log_prefix()
        try:
            self._ensure_authenticated()
            spo2_data = self.client.get_spo2_data(target_date.isoformat())
            if spo2_data:
                logger.info(f"{prefix} 获取 {target_date} 的血氧数据成功，类型: {type(spo2_data).__name__}")
                if isinstance(spo2_data, dict):
                    logger.debug(f"{prefix} 血氧数据键: {list(spo2_data.keys())}")
            else:
                logger.debug(f"{prefix} 获取 {target_date} 的血氧数据为空")
            return spo2_data
        except GarminAuthenticationError:
            raise
        except Exception as e:
            logger.error(f"{prefix} 获取血氧数据失败: {str(e)}")
            return None

    def get_respiration_data(self, target_date: date) -> Optional[Dict[str, Any]]:
        """
        获取呼吸数据

        Args:
            target_date: 目标日期

        Returns:
            呼吸数据字典
        """
        prefix = self._log_prefix()
        try:
            self._ensure_authenticated()
            resp_data = self.client.get_respiration_data(target_date.isoformat())
            if resp_data:
                logger.info(f"{prefix} 获取 {target_date} 的呼吸数据成功，类型: {type(resp_data).__name__}")
                if isinstance(resp_data, dict):
                    logger.debug(f"{prefix} 呼吸数据键: {list(resp_data.keys())}")
            else:
                logger.debug(f"{prefix} 获取 {target_date} 的呼吸数据为空")
            return resp_data
        except GarminAuthenticationError:
            raise
        except Exception as e:
            logger.error(f"{prefix} 获取呼吸数据失败: {str(e)}")
            return None

    def get_max_metrics(self, target_date: date) -> Optional[Dict[str, Any]]:
        """
        获取最大摄氧量(VO2Max)和健身年龄等指标

        Args:
            target_date: 目标日期

        Returns:
            最大指标数据字典，包含 vo2MaxRunning, vo2MaxCycling, fitnessAge 等
        """
        prefix = self._log_prefix()
        try:
            self._ensure_authenticated()
            max_metrics = self.client.get_max_metrics(target_date.isoformat())
            if max_metrics:
                logger.info(f"{prefix} 获取 {target_date} 的最大摄氧量数据成功，类型: {type(max_metrics).__name__}")
                if isinstance(max_metrics, dict):
                    # 记录关键字段
                    vo2max = max_metrics.get('generic', {}).get('vo2MaxPreciseValue') or max_metrics.get('vo2MaxValue')
                    fitness_age = max_metrics.get('generic', {}).get('fitnessAge')
                    logger.info(f"{prefix} VO2Max={vo2max}, 健身年龄={fitness_age}")
            else:
                logger.debug(f"{prefix} 获取 {target_date} 的最大摄氧量数据为空")
            return max_metrics
        except GarminAuthenticationError:
            raise
        except Exception as e:
            logger.error(f"{prefix} 获取最大摄氧量数据失败: {str(e)}")
            return None

    def get_stress_data(self, target_date: date) -> Optional[Dict[str, Any]]:
        """
        获取压力数据

        Args:
            target_date: 目标日期

        Returns:
            压力数据字典
        """
        prefix = self._log_prefix()
        try:
            self._ensure_authenticated()
            # 使用get_all_day_stress获取压力数据（garminconnect库的实际方法名）
            stress_data = self.client.get_all_day_stress(target_date.isoformat())
            return stress_data
        except GarminAuthenticationError:
            raise
        except Exception as e:
            logger.error(f"{prefix} 获取压力数据失败: {str(e)}")
            return None

    # ------------------------------------------------------------------
    # P1a: 新扩展 collector 方法（HRV 时序 / Training Readiness / 设备 / 其他）
    # 所有方法失败只 warn 不抛，保证其他数据不受阻塞
    # ------------------------------------------------------------------

    def get_hrv_data(self, target_date: date) -> Optional[Dict[str, Any]]:
        """HRV 逐夜时序数据（含 hrvReadings 列表）。"""
        prefix = self._log_prefix()
        try:
            self._ensure_authenticated()
            hrv = self.client.get_hrv_data(target_date.isoformat())
            if hrv and isinstance(hrv, dict):
                readings = hrv.get('hrvReadings') or []
                logger.info(f"{prefix} HRV {target_date}: {len(readings)} 读数")
            return hrv
        except GarminAuthenticationError:
            raise
        except Exception as e:
            logger.warning(f"{prefix} 获取 HRV 数据失败: {e}")
            return None

    def get_training_readiness(self, target_date: date) -> Optional[Dict[str, Any]]:
        """Garmin Training Readiness（0-100 + 分级 + 因素分解）。"""
        prefix = self._log_prefix()
        try:
            self._ensure_authenticated()
            data = self.client.get_training_readiness(target_date.isoformat())
            # 有的账户返回 list（每小时更新），取最新一条
            if isinstance(data, list) and data:
                data = data[-1]
            if isinstance(data, dict):
                score = data.get('score')
                level = data.get('level') or data.get('feedbackLong') or data.get('feedbackShort')
                logger.info(f"{prefix} TrainingReadiness {target_date}: score={score} level={level}")
            return data if isinstance(data, dict) else None
        except GarminAuthenticationError:
            raise
        except Exception as e:
            logger.warning(f"{prefix} 获取 Training Readiness 失败: {e}")
            return None

    def get_training_status(self, target_date: date) -> Optional[Dict[str, Any]]:
        """Garmin Training Status（productive/detraining/overreaching/...）。"""
        prefix = self._log_prefix()
        try:
            self._ensure_authenticated()
            data = self.client.get_training_status(target_date.isoformat())
            return data if isinstance(data, dict) else None
        except GarminAuthenticationError:
            raise
        except Exception as e:
            logger.warning(f"{prefix} 获取 Training Status 失败: {e}")
            return None

    def get_endurance_score(self, target_date: date) -> Optional[Dict[str, Any]]:
        """耐力评分。"""
        prefix = self._log_prefix()
        try:
            self._ensure_authenticated()
            data = self.client.get_endurance_score(target_date.isoformat())
            return data if isinstance(data, dict) else None
        except GarminAuthenticationError:
            raise
        except Exception as e:
            logger.warning(f"{prefix} 获取 Endurance Score 失败: {e}")
            return None

    def get_hill_score(self, target_date: date) -> Optional[Dict[str, Any]]:
        """爬坡评分。"""
        prefix = self._log_prefix()
        try:
            self._ensure_authenticated()
            data = self.client.get_hill_score(target_date.isoformat())
            return data if isinstance(data, dict) else None
        except GarminAuthenticationError:
            raise
        except Exception as e:
            logger.warning(f"{prefix} 获取 Hill Score 失败: {e}")
            return None

    def get_race_predictions(self) -> Optional[Dict[str, Any]]:
        """5k / 10k / 半马 / 马拉松 完成时间预测（秒）。"""
        prefix = self._log_prefix()
        try:
            self._ensure_authenticated()
            data = self.client.get_race_predictions()
            return data if isinstance(data, dict) else None
        except GarminAuthenticationError:
            raise
        except Exception as e:
            logger.warning(f"{prefix} 获取 Race Predictions 失败: {e}")
            return None

    def get_hydration_data(self, target_date: date) -> Optional[Dict[str, Any]]:
        """当日水合量（毫升）。"""
        prefix = self._log_prefix()
        try:
            self._ensure_authenticated()
            data = self.client.get_hydration_data(target_date.isoformat())
            return data if isinstance(data, dict) else None
        except GarminAuthenticationError:
            raise
        except Exception as e:
            logger.warning(f"{prefix} 获取 Hydration 失败: {e}")
            return None

    def get_body_composition(self, target_date: date) -> Optional[Dict[str, Any]]:
        """体成分（Garmin Index 秤）。"""
        prefix = self._log_prefix()
        try:
            self._ensure_authenticated()
            data = self.client.get_body_composition(target_date.isoformat())
            return data if isinstance(data, dict) else None
        except GarminAuthenticationError:
            raise
        except Exception as e:
            logger.warning(f"{prefix} 获取 Body Composition 失败: {e}")
            return None

    def get_devices(self) -> Optional[List[Dict[str, Any]]]:
        """Garmin 设备列表（电量/最后同步时间）。"""
        prefix = self._log_prefix()
        try:
            self._ensure_authenticated()
            data = self.client.get_devices()
            if isinstance(data, list):
                logger.info(f"{prefix} 获取到 {len(data)} 个 Garmin 设备")
                return data
            return None
        except GarminAuthenticationError:
            raise
        except Exception as e:
            logger.warning(f"{prefix} 获取 Devices 失败: {e}")
            return None

    def get_activity_hr_in_timezones(self, activity_id: int) -> Optional[List[Dict[str, Any]]]:
        """单次训练的心率区间分布（Z1-Z5）。"""
        prefix = self._log_prefix()
        try:
            self._ensure_authenticated()
            data = self.client.get_activity_hr_in_timezones(activity_id)
            if isinstance(data, list):
                return data
            return None
        except GarminAuthenticationError:
            raise
        except Exception as e:
            logger.warning(f"{prefix} 获取 Activity HR Zones 失败 (id={activity_id}): {e}")
            return None

    def get_all_daily_data(self, target_date: date) -> Dict[str, Any]:
        """
        获取指定日期的所有数据（汇总）

        Args:
            target_date: 目标日期

        Returns:
            包含所有数据的字典
        """
        result = {}

        # 获取用户摘要（包含大部分数据）
        summary = self.get_user_summary(target_date)
        if summary:
            if isinstance(summary, dict):
                result.update(summary)
                logger.debug(f"从get_user_summary获取的数据键: {list(summary.keys())[:20]}")
            else:
                logger.warning(f"get_user_summary返回的不是字典类型: {type(summary)}")
        else:
            logger.warning(f"[用户 {self.user_id}] get_user_summary返回空，将依赖其他API和活动数据")

        # 获取睡眠数据（优先使用独立API，数据更详细）
        sleep_data = self.get_sleep_data(target_date)
        if sleep_data:
            result['sleep'] = sleep_data
            if isinstance(sleep_data, dict):
                logger.debug(f"从get_sleep_data获取的数据键: {list(sleep_data.keys())[:20]}")
            elif isinstance(sleep_data, list):
                logger.debug(f"从get_sleep_data获取的是列表，长度: {len(sleep_data)}")
            else:
                logger.debug(f"从get_sleep_data获取的数据类型: {type(sleep_data)}")
        elif isinstance(summary, dict) and ('sleepScore' in summary or 'sleepScores' in summary):
            # 如果独立API没有数据，但summary中有睡眠数据，使用summary的
            logger.info("使用summary中的睡眠数据")

        # 获取心率数据（优先使用独立API）
        hr_data = self.get_heart_rates(target_date)
        if hr_data:
            result['heart_rate'] = hr_data
            if isinstance(hr_data, dict):
                logger.debug(f"从get_heart_rates获取的数据键: {list(hr_data.keys())[:20]}")
            elif isinstance(hr_data, list):
                logger.debug(f"从get_heart_rates获取的是列表，长度: {len(hr_data)}")
            else:
                logger.debug(f"从get_heart_rates获取的数据类型: {type(hr_data)}")
        elif isinstance(summary, dict) and ('averageHeartRate' in summary or 'avgHeartRate' in summary):
            # 如果独立API没有数据，但summary中有心率数据，使用summary的
            logger.info("使用summary中的心率数据")

        # 获取身体电量
        battery_data = self.get_body_battery(target_date)
        if battery_data:
            result['body_battery'] = battery_data
            if isinstance(battery_data, list):
                logger.debug(f"从get_body_battery获取的是列表，长度: {len(battery_data)}")
            elif isinstance(battery_data, dict):
                logger.debug(f"从get_body_battery获取的数据键: {list(battery_data.keys())[:20]}")

        # 获取压力数据
        stress_data = self.get_stress_data(target_date)
        if stress_data:
            result['stress'] = stress_data
            if isinstance(stress_data, list):
                logger.debug(f"从get_stress_data获取的是列表，长度: {len(stress_data)}")
            elif isinstance(stress_data, dict):
                logger.debug(f"从get_stress_data获取的数据键: {list(stress_data.keys())[:20]}")

        # 获取血氧数据
        spo2_data = self.get_spo2_data(target_date)
        if spo2_data:
            result['spo2'] = spo2_data
            if isinstance(spo2_data, list):
                logger.debug(f"从get_spo2_data获取的是列表，长度: {len(spo2_data)}")
            elif isinstance(spo2_data, dict):
                logger.debug(f"从get_spo2_data获取的数据键: {list(spo2_data.keys())[:20]}")

        # 获取呼吸数据
        resp_data = self.get_respiration_data(target_date)
        if resp_data:
            result['respiration'] = resp_data
            if isinstance(resp_data, list):
                logger.debug(f"从get_respiration_data获取的是列表，长度: {len(resp_data)}")
            elif isinstance(resp_data, dict):
                logger.debug(f"从get_respiration_data获取的数据键: {list(resp_data.keys())[:20]}")

        # 获取最大摄氧量和健康年龄数据
        max_metrics = self.get_max_metrics(target_date)
        if max_metrics:
            result['max_metrics'] = max_metrics
            if isinstance(max_metrics, dict):
                logger.info(f"从get_max_metrics获取的数据键: {list(max_metrics.keys())}")

        # P1a: Training Readiness / Status + 其他
        training_readiness = self.get_training_readiness(target_date)
        if training_readiness:
            result['training_readiness'] = training_readiness

        training_status = self.get_training_status(target_date)
        if training_status:
            result['training_status'] = training_status

        endurance = self.get_endurance_score(target_date)
        if endurance:
            result['endurance_score'] = endurance

        hill = self.get_hill_score(target_date)
        if hill:
            result['hill_score'] = hill

        hydration = self.get_hydration_data(target_date)
        if hydration:
            result['hydration'] = hydration

        # race_predictions 是账户级别，不是按日的（同步时只取一次即可；此处保留每日取）
        race_pred = self.get_race_predictions()
        if race_pred:
            result['race_predictions'] = race_pred

        # HRV 时序（单独在 sync_daily_data 里写表，这里也存 raw 供 parse 用）
        hrv_data = self.get_hrv_data(target_date)
        if hrv_data:
            result['hrv_raw'] = hrv_data

        return result
