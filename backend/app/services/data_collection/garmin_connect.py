"""Garmin Connect数据收集服务（使用社区库garminconnect）"""
import asyncio
from datetime import date, datetime, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from app.models.daily_health import GarminData
from app.schemas.daily_health import GarminDataCreate
import logging

logger = logging.getLogger(__name__)

try:
    from garminconnect import Garmin
    GARMINCONNECT_AVAILABLE = True
except ImportError:
    GARMINCONNECT_AVAILABLE = False
    logger.warning("garminconnect库未安装，请运行: pip install garminconnect")


class GarminAuthenticationError(Exception):
    """Garmin认证错误，用于标识凭证问题"""
    pass


class GarminMFARequiredError(Exception):
    """Garmin需要两步验证"""
    def __init__(self, message: str, client_state: dict):
        super().__init__(message)
        self.client_state = client_state


class GarminConnectService:
    """
    Garmin Connect数据收集服务
    
    使用社区库 garminconnect (https://github.com/cyberjunky/python-garminconnect)
    这个库通过模拟浏览器登录Garmin Connect来获取数据，不需要官方API密钥
    
    安装: pip install garminconnect
    
    支持:
    - 国际版: connect.garmin.com (is_cn=False)
    - 中国版: connect.garmin.cn (is_cn=True)
    """
    
    def __init__(self, email: str, password: str, is_cn: bool = False, user_id: int = None):
        """
        初始化Garmin Connect服务
        
        Args:
            email: Garmin Connect账号邮箱
            password: Garmin Connect账号密码
            is_cn: 是否使用中国服务器 (garmin.cn)，默认False使用国际版
            user_id: 用户ID，用于日志记录
        """
        if not GARMINCONNECT_AVAILABLE:
            raise ImportError(
                "garminconnect库未安装。请运行: pip install garminconnect\n"
                "GitHub: https://github.com/cyberjunky/python-garminconnect"
            )
        
        self.email = email
        self.password = password
        self.is_cn = is_cn
        self.user_id = user_id
        self.client: Optional[Garmin] = None
        self._authenticated = False
        self._mfa_client_state = None  # 用于存储 MFA 状态
    
    def _log_prefix(self) -> str:
        """生成日志前缀，包含用户信息"""
        if self.user_id:
            return f"[用户 {self.user_id}]"
        # 隐藏邮箱中间部分
        email_parts = self.email.split('@')
        if len(email_parts) == 2 and len(email_parts[0]) > 3:
            masked_email = email_parts[0][:2] + '***' + '@' + email_parts[1]
        else:
            masked_email = '***'
        return f"[{masked_email}]"
    
    def _ensure_authenticated(self):
        """确保已认证，认证失败时抛出异常"""
        prefix = self._log_prefix()
        if not self._authenticated or self.client is None:
            try:
                self.client = Garmin(self.email, self.password, is_cn=self.is_cn)
                self.client.login()
                self._authenticated = True
                server_type = "中国版 (garmin.cn)" if self.is_cn else "国际版 (garmin.com)"
                logger.info(f"{prefix} Garmin Connect登录成功 - {server_type}")
            except Exception as e:
                self._authenticated = False
                error_msg = str(e).lower()
                
                # 检查是否需要设置密码
                if 'set password' in error_msg or 'unexpected title' in error_msg:
                    logger.warning(f"{prefix} Garmin账号需要设置密码")
                    raise GarminAuthenticationError(
                        "Garmin账号需要设置密码！请先访问 https://connect.garmin.com 登录并按提示完成密码设置，然后再尝试同步。"
                    ) from e
                
                # 将登录失败转换为明确的认证错误
                if any(kw in error_msg for kw in ['login', 'auth', '401', 'unauthorized', 'credential', 'password', 'oauth']):
                    logger.error(f"{prefix} Garmin登录失败: {e}")
                    raise GarminAuthenticationError(f"Garmin登录失败: {e}") from e
                logger.error(f"{prefix} Garmin认证异常: {e}")
                raise
    
    def test_connection_with_mfa(self) -> Dict[str, Any]:
        """
        测试连接，支持两步验证（MFA）
        
        Returns:
            dict: {
                "success": bool,
                "mfa_required": bool,  # 是否需要 MFA
                "client_state": dict,  # 如果需要 MFA，返回客户端状态用于恢复登录
                "message": str
            }
        """
        prefix = self._log_prefix()
        try:
            # 创建支持 MFA 提前返回的客户端
            self.client = Garmin(
                self.email, 
                self.password, 
                is_cn=self.is_cn,
                return_on_mfa=True  # 需要 MFA 时提前返回
            )
            
            result = self.client.login()
            
            # 检查是否需要 MFA
            # 如果返回的是 tuple 且第一个元素是 dict 包含 client_state，说明需要 MFA
            if result and isinstance(result, tuple) and len(result) >= 2:
                token1, token2 = result
                # 如果没有获取到完整的 token，可能需要 MFA
                if not self.client.garth.oauth2_token:
                    # 尝试获取 client_state
                    client_state = getattr(self.client.garth, '_client_state', None)
                    if client_state:
                        self._mfa_client_state = client_state
                        server_type = "中国版" if self.is_cn else "国际版"
                        logger.info(f"{prefix} Garmin {server_type} 需要两步验证")
                        return {
                            "success": False,
                            "mfa_required": True,
                            "client_state": client_state,
                            "message": "🔐 需要两步验证！请输入您 Garmin 账号绑定的验证器应用中的验证码。"
                        }
            
            # 登录成功
            self._authenticated = True
            server_type = "中国版 (garmin.cn)" if self.is_cn else "国际版 (garmin.com)"
            logger.info(f"{prefix} Garmin Connect {server_type} 登录成功")
            
            return {
                "success": True,
                "mfa_required": False,
                "message": "✅ 密码正确！Garmin账号连接成功，可以保存凭证了。"
            }
            
        except Exception as e:
            error_msg = str(e).lower()
            
            # 检查是否需要 MFA（某些版本的库可能通过异常表示需要 MFA）
            if 'mfa' in error_msg or 'two-factor' in error_msg or 'verification' in error_msg:
                # 获取 client_state
                client_state = None
                if self.client and hasattr(self.client, 'garth'):
                    client_state = getattr(self.client.garth, '_client_state', None)
                
                if client_state:
                    self._mfa_client_state = client_state
                    return {
                        "success": False,
                        "mfa_required": True,
                        "client_state": client_state,
                        "message": "🔐 需要两步验证！请输入验证码。"
                    }
            
            # 检查是否需要设置密码
            if 'set password' in error_msg or 'unexpected title' in error_msg:
                return {
                    "success": False,
                    "mfa_required": False,
                    "message": "⚠️ Garmin账号需要设置密码！请先访问 connect.garmin.com 登录并完成密码设置。"
                }
            
            # 认证错误
            if any(kw in error_msg for kw in ['401', 'unauthorized', 'credential', 'password', 'login', 'auth']):
                return {
                    "success": False,
                    "mfa_required": False,
                    "message": "❌ 密码错误或账号无效！请检查邮箱和密码是否正确。"
                }
            
            logger.error(f"{prefix} 测试连接失败: {e}")
            return {
                "success": False,
                "mfa_required": False,
                "message": f"❌ 连接失败: {str(e)}"
            }
    
    def resume_login_with_mfa(self, client_state: Dict[str, Any], mfa_code: str) -> Dict[str, Any]:
        """
        使用 MFA 验证码恢复登录
        
        Args:
            client_state: test_connection_with_mfa 返回的客户端状态
            mfa_code: 用户输入的 MFA 验证码
            
        Returns:
            dict: {
                "success": bool,
                "message": str
            }
        """
        prefix = self._log_prefix()
        try:
            if self.client is None:
                # 如果客户端不存在，需要重新创建
                self.client = Garmin(self.email, self.password, is_cn=self.is_cn)
            
            # 使用验证码恢复登录
            self.client.resume_login(client_state, mfa_code)
            self._authenticated = True
            
            server_type = "中国版" if self.is_cn else "国际版"
            logger.info(f"{prefix} Garmin {server_type} MFA 验证成功")
            
            return {
                "success": True,
                "message": "✅ 验证成功！Garmin账号连接成功，可以保存凭证了。"
            }
            
        except Exception as e:
            error_msg = str(e).lower()
            
            if 'invalid' in error_msg or 'incorrect' in error_msg or 'wrong' in error_msg:
                return {
                    "success": False,
                    "message": "❌ 验证码错误！请检查并重新输入。"
                }
            
            logger.error(f"{prefix} MFA 验证失败: {e}")
            return {
                "success": False,
                "message": f"❌ 验证失败: {str(e)}"
            }
    
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
        
        return result
    
    def parse_to_garmin_data_create(
        self,
        raw_data: Dict[str, Any],
        user_id: int,
        record_date: date
    ) -> GarminDataCreate:
        """
        将Garmin Connect返回的原始数据解析为GarminDataCreate
        
        Args:
            raw_data: Garmin Connect返回的原始数据（可能包含summary、sleep、heart_rate等）
            user_id: 用户ID
            record_date: 记录日期
            
        Returns:
            GarminDataCreate对象
        """
        # 调试：打印原始数据结构（仅前1000字符）
        import json
        raw_data_str = json.dumps(raw_data, indent=2, default=str)[:2000]
        logger.debug(f"解析Garmin数据，原始数据结构（前2000字符）:\n{raw_data_str}")
        
        # 从get_user_summary获取的数据在根级别
        summary = raw_data.copy() if isinstance(raw_data, dict) else {}
        
        # 处理睡眠数据（可能来自get_sleep_data或summary）
        sleep_data_raw = raw_data.get('sleep') if isinstance(raw_data, dict) else None
        
        # 如果sleep_data是列表，取第一个元素；如果是字典，直接使用；否则为空字典
        if isinstance(sleep_data_raw, list) and sleep_data_raw:
            sleep_data = sleep_data_raw[0] if isinstance(sleep_data_raw[0], dict) else {}
        elif isinstance(sleep_data_raw, dict):
            sleep_data = sleep_data_raw
        else:
            sleep_data = {}
        
        # 辅助函数：安全获取嵌套字典值（支持多层嵌套）
        def safe_get_nested(data, *keys, default=None):
            """安全获取多层嵌套字典值"""
            if not isinstance(data, dict):
                return default
            for key in keys:
                if not isinstance(data, dict):
                    return default
                data = data.get(key)
                if data is None:
                    return default
            return data if data is not None else default
        
        # 尝试多种方式获取睡眠分数
        sleep_score = None
        sleep_duration_seconds = 0
        deep_sleep_seconds = 0
        rem_sleep_seconds = 0
        light_sleep_seconds = 0
        awake_seconds = 0
        nap_seconds = 0
        avg_heart_rate_during_sleep = None
        hrv = None  # HRV数据，优先从睡眠数据获取
        
        if isinstance(sleep_data, dict) and sleep_data:
            # Garmin睡眠数据结构:
            # sleep_data = {
            #   'dailySleepDTO': {
            #     'sleepTimeSeconds': 29280,
            #     'sleepScores': {'overall': {'value': 87}},
            #     'deepSleepSeconds': 3720,
            #     ...
            #   },
            #   'restingHeartRate': 51,
            #   ...
            # }
            
            # 打印睡眠数据的顶层键
            logger.info(f"睡眠数据顶层键: {list(sleep_data.keys())}")
            
            # 获取 dailySleepDTO
            daily_sleep_dto = sleep_data.get('dailySleepDTO', {})
            if not isinstance(daily_sleep_dto, dict):
                daily_sleep_dto = {}
            
            # 打印 dailySleepDTO 的键和睡眠分数相关字段
            if daily_sleep_dto:
                logger.info(f"dailySleepDTO 键: {list(daily_sleep_dto.keys())}")
                sleep_scores = daily_sleep_dto.get('sleepScores')
                if sleep_scores:
                    logger.info(f"sleepScores 内容: {sleep_scores}")
            else:
                logger.info("dailySleepDTO 为空")
            
            # 获取睡眠分数 - 正确的路径是 dailySleepDTO.sleepScores.overall.value
            sleep_score = (
                safe_get_nested(daily_sleep_dto, 'sleepScores', 'overall', 'value') or
                safe_get_nested(sleep_data, 'sleepScores', 'overall', 'value') or
                daily_sleep_dto.get('sleepScore') or
                sleep_data.get('sleepScore') or
                safe_get_nested(daily_sleep_dto, 'sleepScores', 'overall') or
                sleep_data.get('overallSleepScore')
            )
            
            # 如果sleep_score是字典（如 {'value': 87, 'qualifierKey': 'GOOD'}），提取value
            if isinstance(sleep_score, dict):
                sleep_score = sleep_score.get('value')
            
            logger.debug(f"提取的睡眠分数: {sleep_score}")
            
            # 睡眠时长（秒）- 从 dailySleepDTO 获取
            sleep_duration_seconds = (
                daily_sleep_dto.get('sleepTimeSeconds') or
                sleep_data.get('sleepTimeSeconds') or
                0
            )
            
            # 睡眠阶段数据 - 从 dailySleepDTO 获取
            deep_sleep_seconds = daily_sleep_dto.get('deepSleepSeconds', 0) or 0
            rem_sleep_seconds = daily_sleep_dto.get('remSleepSeconds', 0) or 0
            light_sleep_seconds = daily_sleep_dto.get('lightSleepSeconds', 0) or 0
            awake_seconds = daily_sleep_dto.get('awakeSleepSeconds', 0) or 0
            
            # 小睡时长（秒）- 从 dailySleepDTO 获取
            nap_seconds = daily_sleep_dto.get('napTimeSeconds', 0) or 0
            
            # 睡眠期间平均心率
            avg_heart_rate_during_sleep = (
                daily_sleep_dto.get('avgHeartRate') or
                sleep_data.get('restingHeartRate')
            )
            
            # HRV数据 - 从睡眠数据中获取
            # avgOvernightHrv 是夜间平均HRV值
            if hrv is None:
                hrv = sleep_data.get('avgOvernightHrv')
            
            logger.info(f"解析睡眠数据: 分数={sleep_score}, 时长秒={sleep_duration_seconds}, 深睡={deep_sleep_seconds}, REM={rem_sleep_seconds}, HRV={hrv}")
        else:
            logger.warning(f"睡眠数据为空或格式不正确: type={type(sleep_data)}, 值={sleep_data}")
        
        # 如果从sleep_data没有获取到，尝试从summary获取
        if isinstance(summary, dict):
            if sleep_score is None:
                score_val = (
                    summary.get('sleepScore') or
                    safe_get_nested(summary, 'sleepScores', 'overall', 'value') or
                    safe_get_nested(summary, 'sleepScores', 'overall') or
                    summary.get('overallSleepScore') or
                    summary.get('sleepQualityScore')
                )
                # 如果是字典，提取value
                if isinstance(score_val, dict):
                    sleep_score = score_val.get('value')
                else:
                    sleep_score = score_val
            if sleep_duration_seconds == 0:
                sleep_millis = summary.get('sleepTimeMillis')
                sleep_duration_seconds = (
                    summary.get('sleepTimeSeconds') or
                    summary.get('sleepDurationSeconds') or
                    summary.get('sleepingSeconds') or
                    (sleep_millis / 1000 if sleep_millis else 0) or
                    summary.get('totalSleepTimeSeconds') or
                    0
                )
            if deep_sleep_seconds == 0:
                deep_sleep_seconds = summary.get('deepSleepSeconds', 0) or summary.get('deepSleepSecondsOvernight', 0) or 0
            if rem_sleep_seconds == 0:
                rem_sleep_seconds = summary.get('remSleepSeconds', 0) or summary.get('remSleepSecondsOvernight', 0) or 0
            if light_sleep_seconds == 0:
                light_sleep_seconds = summary.get('lightSleepSeconds', 0) or summary.get('lightSleepSecondsOvernight', 0) or 0
            if awake_seconds == 0:
                awake_seconds = summary.get('awakeSleepSeconds', 0) or summary.get('awakeSleepSecondsOvernight', 0) or 0
        
        # 处理心率数据（可能来自get_heart_rates或summary）
        hr_data_raw = None
        if isinstance(raw_data, dict):
            hr_data_raw = raw_data.get('heart_rate') or raw_data.get('heartRates')
        
        # 如果hr_data是列表，取第一个元素；如果是字典，直接使用；否则为空字典
        if isinstance(hr_data_raw, list) and hr_data_raw:
            hr_data = hr_data_raw[0] if isinstance(hr_data_raw[0], dict) else {}
        elif isinstance(hr_data_raw, dict):
            hr_data = hr_data_raw
        else:
            hr_data = {}
        
        avg_hr = None
        resting_hr = None
        max_hr = None
        min_hr = None
        
        if isinstance(hr_data, dict) and hr_data:
            # 从独立的heart_rate数据中提取
            hr_values = hr_data.get('heartRateValues')
            first_hr_value = None
            if isinstance(hr_values, list) and hr_values and isinstance(hr_values[0], dict):
                first_hr_value = hr_values[0].get('value')
            
            avg_hr = (
                hr_data.get('averageHeartRate') or
                hr_data.get('avg') or
                hr_data.get('avgHeartRate') or
                hr_data.get('average') or
                first_hr_value
            )
            resting_hr = (
                hr_data.get('restingHeartRate') or
                hr_data.get('resting') or
                hr_data.get('restingHeartRateValue')
            )
            max_hr = hr_data.get('maxHeartRate') or hr_data.get('max')
            min_hr = hr_data.get('minHeartRate') or hr_data.get('min')
        
        # 如果从hr_data没有获取到，尝试从summary获取
        if isinstance(summary, dict):
            if avg_hr is None:
                avg_hr = (
                    summary.get('averageHeartRate') or
                    summary.get('avgHeartRate') or
                    summary.get('avg') or
                    summary.get('average') or
                    summary.get('heartRateAverage')
                )
            if resting_hr is None:
                resting_hr = (
                    summary.get('restingHeartRate') or
                    summary.get('resting') or
                    summary.get('restingHeartRateValue')
                )
            if max_hr is None:
                max_hr = summary.get('maxHeartRate') or summary.get('max')
            if min_hr is None:
                min_hr = summary.get('minHeartRate') or summary.get('min')
        
        # 如果还没有获取到静息心率，尝试从睡眠数据获取
        if resting_hr is None and isinstance(sleep_data, dict):
            resting_hr = sleep_data.get('restingHeartRate')
            if resting_hr:
                logger.info(f"从睡眠数据获取静息心率: {resting_hr}")
        
        # 如果还没有获取到平均心率，尝试从睡眠数据获取
        if avg_hr is None and isinstance(sleep_data, dict):
            daily_sleep_dto = sleep_data.get('dailySleepDTO', {})
            if isinstance(daily_sleep_dto, dict):
                avg_hr = daily_sleep_dto.get('avgHeartRate')
                if avg_hr:
                    logger.info(f"从睡眠数据获取平均心率: {avg_hr}")
        
        # HRV数据 - 如果从睡眠数据没有获取到，尝试从summary获取
        if hrv is None and isinstance(summary, dict):
            hrv = summary.get('hrv') or safe_get_nested(summary, 'hrvStatus', 'hrv') or summary.get('avgOvernightHrv')
        
        logger.debug(f"最终HRV值: {hrv}")
        
        # 身体电量数据（可能来自get_body_battery或summary）
        battery_data_raw = None
        if isinstance(raw_data, dict):
            battery_data_raw = raw_data.get('body_battery') or raw_data.get('bodyBattery')
        
        logger.info(f"身体电量原始数据类型: {type(battery_data_raw)}")
        if battery_data_raw:
            if isinstance(battery_data_raw, list):
                logger.info(f"身体电量原始数据(列表)长度: {len(battery_data_raw)}")
                if battery_data_raw:
                    sample = battery_data_raw[0] if len(battery_data_raw) > 0 else None
                    logger.info(f"身体电量第一个元素: {sample}")
            elif isinstance(battery_data_raw, dict):
                logger.info(f"身体电量原始数据(字典)键: {list(battery_data_raw.keys())}")
        
        # 如果battery_data是列表，可能需要从中提取统计值
        battery_data = {}
        charged = None
        drained = None
        most_charged = None
        lowest = None
        
        if isinstance(battery_data_raw, list) and battery_data_raw:
            # Garmin返回的是一个时间序列列表，每个元素包含 bodyBatteryLevel 等
            # 需要遍历找到 charged/drained 或计算 most_charged/lowest
            battery_levels = []
            for item in battery_data_raw:
                if isinstance(item, dict):
                    level = item.get('bodyBatteryLevel') or item.get('level') or item.get('value')
                    if level is not None:
                        battery_levels.append(level)
                    # 有些格式直接包含统计数据
                    if item.get('charged') is not None:
                        charged = item.get('charged')
                    if item.get('drained') is not None:
                        drained = item.get('drained')
            
            if battery_levels:
                most_charged = max(battery_levels)
                lowest = min(battery_levels)
                # 估算充电和消耗（简化计算）
                if charged is None and len(battery_levels) >= 2:
                    # 计算总充电量（上升的部分之和）
                    total_charged = 0
                    total_drained = 0
                    for i in range(1, len(battery_levels)):
                        diff = battery_levels[i] - battery_levels[i-1]
                        if diff > 0:
                            total_charged += diff
                        else:
                            total_drained += abs(diff)
                    charged = total_charged if total_charged > 0 else None
                    drained = total_drained if total_drained > 0 else None
            
            logger.info(f"从列表计算: most_charged={most_charged}, lowest={lowest}, charged={charged}, drained={drained}")
            
        elif isinstance(battery_data_raw, dict):
            battery_data = battery_data_raw
            charged = battery_data.get('charged') or battery_data.get('bodyBatteryCharged') or battery_data.get('chargedValue')
            drained = battery_data.get('drained') or battery_data.get('bodyBatteryDrained') or battery_data.get('drainedValue')
            most_charged = battery_data.get('mostCharged') or battery_data.get('bodyBatteryMostCharged') or battery_data.get('mostChargedValue')
            lowest = battery_data.get('lowest') or battery_data.get('bodyBatteryLowest') or battery_data.get('lowestValue')
        
        # 如果还没有获取到，尝试从 summary 获取
        if most_charged is None and isinstance(summary, dict):
            charged = charged or summary.get('bodyBatteryChargedValue') or summary.get('bodyBatteryCharged')
            drained = drained or summary.get('bodyBatteryDrainedValue') or summary.get('bodyBatteryDrained')
            most_charged = summary.get('bodyBatteryMostRecentValue') or summary.get('bodyBatteryHighestValue') or summary.get('bodyBatteryMostCharged')
            lowest = summary.get('bodyBatteryLowestValue') or summary.get('bodyBatteryLowest')
        
        logger.info(f"最终身体电量: charged={charged}, drained={drained}, most_charged={most_charged}, lowest={lowest}")
        
        # 压力数据（可能来自get_all_day_stress或summary）
        stress_data_raw = None
        if isinstance(raw_data, dict):
            stress_data_raw = raw_data.get('stress')
        
        stress_level = None
        if isinstance(stress_data_raw, list) and stress_data_raw:
            # get_all_day_stress返回的是数组，需要计算平均值
            stress_values = [s.get('stressLevelValue', s.get('value', 0)) for s in stress_data_raw if isinstance(s, dict)]
            stress_level = sum(stress_values) / len(stress_values) if stress_values else None
        elif isinstance(stress_data_raw, dict) and stress_data_raw:
            # get_all_day_stress返回字典，包含avgStressLevel和maxStressLevel
            stress_level = (
                stress_data_raw.get('avgStressLevel') or
                stress_data_raw.get('averageStressLevel') or
                stress_data_raw.get('stressLevel') or
                stress_data_raw.get('value') or
                stress_data_raw.get('stressLevelValue')
            )
        
        # 如果从stress数据中没有获取到，尝试从summary获取
        if stress_level is None and isinstance(summary, dict):
            stress_level = (
                summary.get('averageStressLevel') or
                summary.get('avgStressLevel') or
                summary.get('stressLevel') or
                summary.get('stress')
            )
        
        logger.debug(f"提取的压力水平: {stress_level} (来源: {'stress数据' if stress_data_raw else 'summary' if isinstance(summary, dict) else '无'})")
        
        # 活动数据（从summary获取）
        steps = None
        calories = None
        active_minutes = None
        
        if isinstance(summary, dict):
            # 步数：优先使用totalSteps
            steps = (
                summary.get('totalSteps') or 
                summary.get('steps') or 
                safe_get_nested(summary, 'stepGoal', 'steps')
            )
            # 卡路里：优先使用totalKilocalories
            calories = (
                summary.get('totalKilocalories') or
                summary.get('activeKilocalories') or
                summary.get('calories') or 
                summary.get('caloriesBurned') or 
                summary.get('totalCalories') or
                safe_get_nested(summary, 'netCalorieGoal', 'calories')
            )
            moderate_mins = summary.get('moderateIntensityMinutes') or summary.get('moderateActivityMinutes') or 0
            vigorous_mins = summary.get('vigorousIntensityMinutes') or summary.get('vigorousActivityMinutes') or 0
            highly_active_seconds = summary.get('highlyActiveSeconds') or 0
            active_minutes = summary.get('activeMinutes') or (highly_active_seconds // 60 if highly_active_seconds else 0) or (moderate_mins + vigorous_mins) or 0
        
        # 安全的数值转换函数
        def safe_int(value):
            """安全地将值转换为整数，如果是字典或列表则返回None"""
            if value is None:
                return None
            if isinstance(value, (int, float)):
                return int(value)
            if isinstance(value, str):
                try:
                    return int(float(value))
                except (ValueError, TypeError):
                    return None
            # 如果是字典或列表，尝试提取数值
            if isinstance(value, dict):
                # 尝试常见的数值字段名
                for key in ['value', 'amount', 'count', 'total', 'average', 'avg']:
                    if key in value and isinstance(value[key], (int, float)):
                        return int(value[key])
                return None
            return None
        
        def safe_float(value):
            """安全地将值转换为浮点数，如果是字典或列表则返回None"""
            if value is None:
                return None
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str):
                try:
                    return float(value)
                except (ValueError, TypeError):
                    return None
            if isinstance(value, dict):
                for key in ['value', 'amount', 'average', 'avg']:
                    if key in value and isinstance(value[key], (int, float)):
                        return float(value[key])
                return None
            return None
        
        # 睡眠时间转换（秒转分钟，处理毫秒）
        def seconds_to_minutes(value):
            if not value:
                return None
            if isinstance(value, (int, float)):
                # 如果是毫秒，先转换为秒
                if value > 86400:  # 如果大于一天的秒数，可能是毫秒
                    value = value / 1000
                return int(value // 60)
            return None
        
        # 解析新增字段
        # HRV状态
        hrv_status = None
        hrv_7day_avg = None
        if isinstance(sleep_data, dict):
            hrv_status = sleep_data.get('hrvStatus')
            if isinstance(hrv_status, dict):
                hrv_status = hrv_status.get('status') or hrv_status.get('hrvStatus')
            # 7天平均HRV - 从weeklyAverages或直接值
            hrv_7day_avg = safe_get_nested(sleep_data, 'hrvData', 'weeklyAvg') or sleep_data.get('hrvWeeklyAverage')
        
        # 强度活动时间
        moderate_intensity_mins = 0
        vigorous_intensity_mins = 0
        intensity_goal = None
        if isinstance(summary, dict):
            moderate_intensity_mins = summary.get('moderateIntensityMinutes', 0) or 0
            vigorous_intensity_mins = summary.get('vigorousIntensityMinutes', 0) or 0
            intensity_goal = summary.get('intensityMinutesGoal') or summary.get('weeklyIntensityMinutesGoal')
        
        # 卡路里详细分类
        active_cals = None
        bmr_cals = None
        if isinstance(summary, dict):
            active_cals = summary.get('activeKilocalories') or summary.get('activeCalories')
            bmr_cals = summary.get('bmrKilocalories') or summary.get('restingCalories') or summary.get('bmrCalories')
        
        # 呼吸数据
        avg_resp_awake = None
        avg_resp_sleep = None
        lowest_resp = None
        highest_resp = None
        if isinstance(sleep_data, dict):
            daily_dto = sleep_data.get('dailySleepDTO', {})
            if isinstance(daily_dto, dict):
                avg_resp_sleep = daily_dto.get('avgRespirationValue') or daily_dto.get('averageRespirationValue')
                lowest_resp = daily_dto.get('lowestRespirationValue')
                highest_resp = daily_dto.get('highestRespirationValue')
        if isinstance(summary, dict):
            avg_resp_awake = summary.get('avgWakingRespirationValue') or summary.get('averageRespirationValue')
            if lowest_resp is None:
                lowest_resp = summary.get('lowestRespirationValue')
            if highest_resp is None:
                highest_resp = summary.get('highestRespirationValue')
        
        # 血氧数据
        spo2_avg = None
        spo2_min = None
        spo2_max = None
        if isinstance(summary, dict):
            spo2_avg = summary.get('averageSpO2') or summary.get('avgSpO2')
            spo2_min = summary.get('lowestSpO2') or summary.get('minSpO2')
            spo2_max = summary.get('highestSpO2') or summary.get('maxSpO2')
        
        # VO2 Max
        vo2max_run = None
        vo2max_cycle = None
        if isinstance(summary, dict):
            vo2max_run = summary.get('vo2MaxRunning') or summary.get('vo2Max')
            vo2max_cycle = summary.get('vo2MaxCycling')
        
        # 楼层和距离
        floors = None
        floors_goal_val = None
        distance = None
        if isinstance(summary, dict):
            floors = summary.get('floorsAscended') or summary.get('floorsClimbed')
            floors_goal_val = summary.get('floorsAscendedGoal') or summary.get('floorsGoal')
            distance = summary.get('totalDistanceMeters') or summary.get('distanceInMeters')
        
        # 记录解析结果用于调试
        logger.info(f"解析结果 - 睡眠分数: {sleep_score}, 睡眠时长(秒): {sleep_duration_seconds}, 静息心率: {resting_hr}, 平均心率: {avg_hr}")
        
        result = GarminDataCreate(
            user_id=user_id,
            record_date=record_date,
            avg_heart_rate=safe_int(avg_hr),
            max_heart_rate=safe_int(max_hr),
            min_heart_rate=safe_int(min_hr),
            resting_heart_rate=safe_int(resting_hr),
            hrv=safe_float(hrv),
            hrv_status=hrv_status,
            hrv_7day_avg=safe_float(hrv_7day_avg),
            sleep_score=safe_int(sleep_score),
            total_sleep_duration=seconds_to_minutes(sleep_duration_seconds),
            deep_sleep_duration=seconds_to_minutes(deep_sleep_seconds),
            rem_sleep_duration=seconds_to_minutes(rem_sleep_seconds),
            light_sleep_duration=seconds_to_minutes(light_sleep_seconds),
            awake_duration=seconds_to_minutes(awake_seconds),
            nap_duration=seconds_to_minutes(nap_seconds),
            body_battery_charged=safe_int(charged),
            body_battery_drained=safe_int(drained),
            body_battery_most_charged=safe_int(most_charged),
            body_battery_lowest=safe_int(lowest),
            stress_level=safe_int(stress_level),
            steps=safe_int(steps),
            calories_burned=safe_int(calories),
            active_calories=safe_int(active_cals),
            bmr_calories=safe_int(bmr_cals),
            active_minutes=safe_int(active_minutes),
            intensity_minutes_goal=safe_int(intensity_goal),
            moderate_intensity_minutes=safe_int(moderate_intensity_mins),
            vigorous_intensity_minutes=safe_int(vigorous_intensity_mins),
            avg_respiration_awake=safe_float(avg_resp_awake),
            avg_respiration_sleep=safe_float(avg_resp_sleep),
            lowest_respiration=safe_float(lowest_resp),
            highest_respiration=safe_float(highest_resp),
            spo2_avg=safe_float(spo2_avg),
            spo2_min=safe_float(spo2_min),
            spo2_max=safe_float(spo2_max),
            vo2max_running=safe_float(vo2max_run),
            vo2max_cycling=safe_float(vo2max_cycle),
            floors_climbed=safe_int(floors),
            floors_goal=safe_int(floors_goal_val),
            distance_meters=safe_float(distance),
        )
        
        return result
    
    def sync_daily_data(
        self,
        db: Session,
        user_id: int,
        target_date: date
    ) -> Optional[GarminData]:
        """
        同步指定日期的数据到数据库
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            target_date: 目标日期
            
        Returns:
            保存的GarminData对象，如果失败返回None
        """
        prefix = self._log_prefix()
        try:
            # 获取所有数据
            logger.info(f"{prefix} 开始获取 {target_date} 的数据...")
            raw_data = self.get_all_daily_data(target_date)
            
            if not raw_data:
                logger.warning(f"{prefix} 未获取到 {target_date} 的数据（raw_data为空）")
                return None
            
            logger.info(f"{prefix} 获取到 {target_date} 的原始数据，键数量: {len(raw_data) if isinstance(raw_data, dict) else 'N/A'}")
            
            # 解析数据
            logger.info(f"{prefix} 开始解析 {target_date} 的数据...")
            garmin_data = self.parse_to_garmin_data_create(raw_data, user_id, target_date)
            
            logger.info(f"{prefix} 解析完成，步数: {garmin_data.steps}, 心率: {garmin_data.resting_heart_rate}")
            
            # 保存到数据库
            logger.info(f"{prefix} 开始保存 {target_date} 的数据到数据库...")
            from app.services.data_collection.garmin_service import GarminService
            garmin_service = GarminService()
            result = garmin_service.save_garmin_data(db, garmin_data)
            
            logger.info(f"{prefix} 成功保存 {target_date} 的数据，ID: {result.id}")
            
            # 同步心率采样数据
            self._sync_heart_rate_samples(db, user_id, target_date)
            
            return result
            
        except Exception as e:
            import traceback
            logger.error(f"{prefix} 同步Garmin数据失败: {str(e)}")
            logger.error(f"{prefix} 详细错误: {traceback.format_exc()}")
            return None
    
    def _sync_heart_rate_samples(
        self,
        db: Session,
        user_id: int,
        target_date: date
    ) -> int:
        """
        同步心率采样数据（每15分钟一个点）
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            target_date: 目标日期
            
        Returns:
            保存的采样点数量
        """
        prefix = self._log_prefix()
        try:
            # 获取心率时间序列数据
            hr_data = self.get_heart_rates(target_date)
            
            if not hr_data:
                logger.debug(f"{prefix} 未获取到 {target_date} 的心率时间序列数据")
                return 0
            
            # 解析心率数据
            hr_values = hr_data.get("heartRateValues") or []
            if not hr_values:
                logger.debug(f"{prefix} {target_date} 的心率时间序列数据为空")
                return 0
            
            from app.models.daily_health import HeartRateSample
            from datetime import time as dt_time
            
            # 按15分钟间隔采样
            samples_by_slot = {}  # key: "HH:MM" (每15分钟一个slot)
            
            for item in hr_values:
                try:
                    if isinstance(item, (list, tuple)) and len(item) >= 2:
                        timestamp_ms = item[0]
                        hr_value = item[1]
                        
                        if hr_value is None or hr_value <= 0:
                            continue
                        
                        # 转换时间戳
                        dt = datetime.fromtimestamp(timestamp_ms / 1000)
                        
                        # 计算15分钟时间槽
                        slot_minute = (dt.minute // 15) * 15
                        slot_key = f"{dt.hour:02d}:{slot_minute:02d}"
                        
                        # 每个时间槽只保留第一个值
                        if slot_key not in samples_by_slot:
                            samples_by_slot[slot_key] = {
                                "time": dt_time(dt.hour, slot_minute),
                                "value": int(hr_value)
                            }
                except (ValueError, TypeError, IndexError):
                    continue
            
            if not samples_by_slot:
                return 0
            
            # 删除该日期已有的采样数据
            db.query(HeartRateSample).filter(
                HeartRateSample.user_id == user_id,
                HeartRateSample.record_date == target_date
            ).delete()
            
            # 批量插入新数据
            samples_to_insert = []
            for slot_key, data in sorted(samples_by_slot.items()):
                samples_to_insert.append(HeartRateSample(
                    user_id=user_id,
                    record_date=target_date,
                    sample_time=data["time"],
                    heart_rate=data["value"],
                    source="garmin"
                ))
            
            db.bulk_save_objects(samples_to_insert)
            db.commit()
            
            logger.info(f"{prefix} 保存了 {target_date} 的 {len(samples_to_insert)} 个心率采样点")
            return len(samples_to_insert)
            
        except Exception as e:
            logger.warning(f"{prefix} 同步心率采样数据失败: {e}")
            return 0
    
    def sync_date_range(
        self,
        db: Session,
        user_id: int,
        start_date: date,
        end_date: date
    ) -> Dict[str, Any]:
        """
        批量同步日期范围的数据
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            同步结果统计
        """
        results = []
        errors = []
        current_date = start_date
        
        while current_date <= end_date:
            try:
                result = self.sync_daily_data(db, user_id, current_date)
                if result:
                    results.append({
                        "date": current_date.isoformat(),
                        "status": "success",
                        "data_id": result.id
                    })
                else:
                    errors.append({
                        "date": current_date.isoformat(),
                        "status": "no_data"
                    })
            except GarminAuthenticationError:
                # 认证错误需要向上传递，让调用者处理
                raise
            except Exception as e:
                errors.append({
                    "date": current_date.isoformat(),
                    "status": "error",
                    "error": str(e)
                })
            
            current_date += timedelta(days=1)
            
            # 避免请求过快，添加小延迟
            import time
            time.sleep(0.8)  # 稍微增加延迟，避免被Garmin限制
        
        return {
            "success_count": len(results),
            "error_count": len(errors),
            "results": results,
            "errors": errors
        }

