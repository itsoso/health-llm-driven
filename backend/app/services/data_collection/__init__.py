"""数据收集服务"""
from app.services.data_collection.garmin_service import GarminService, DataCollectionService
from app.services.data_collection.medical_exam_import import MedicalExamImportService

# 可选：Garmin Connect集成（需要安装garminconnect库）
try:
    from app.services.data_collection.garmin_connect import GarminConnectService
    __all__ = [
        "GarminService",
        "DataCollectionService",
        "GarminConnectService",
        "MedicalExamImportService",
    ]
except ImportError:
    __all__ = [
        "GarminService",
        "DataCollectionService",
        "MedicalExamImportService",
    ]

