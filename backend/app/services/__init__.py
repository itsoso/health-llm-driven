"""服务层.

Keep top-level service exports lazy so importing a small service module does
not pull optional integrations such as Garmin/httpx into lightweight tests.
"""

__all__ = [
    "DataCollectionService",
    "HealthAnalysisService",
    "GoalManagementService",
]


def __getattr__(name):
    if name == "DataCollectionService":
        from app.services.data_collection import DataCollectionService

        return DataCollectionService
    if name == "HealthAnalysisService":
        from app.services.health_analysis import HealthAnalysisService

        return HealthAnalysisService
    if name == "GoalManagementService":
        from app.services.goal_management import GoalManagementService

        return GoalManagementService
    raise AttributeError(f"module 'app.services' has no attribute {name!r}")
