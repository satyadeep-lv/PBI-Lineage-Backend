import asyncio

from app.core.exceptions import AppException
from app.schemas.gateway import GatewayDatasource
from app.schemas.lineage_graph import LineageGraph, LineageGraphBuildRequest
from app.schemas.physical_source import PhysicalSourceWarning
from app.schemas.scan_job import LiveLineageScanRequest
from app.services.gateway_service import GatewayService
from app.services.lineage_graph_service import LineageGraphService
from app.services.physical_source_service import PhysicalSourceDiscoveryService
from app.services.report_definition_service import ReportDefinitionService
from app.services.report_semantic_lineage_service import ReportSemanticLineageService
from app.services.semantic_model_definition_service import (
    SemanticModelDefinitionService,
)


class LiveLineageScanService:
    def __init__(self) -> None:
        self.semantic_model_service = SemanticModelDefinitionService()
        self.report_definition_service = ReportDefinitionService()
        self.report_lineage_service = ReportSemanticLineageService()
        self.gateway_service = GatewayService()

    async def build_graph(
        self,
        request: LiveLineageScanRequest,
        *,
        fabric_access_token: str,
        powerbi_access_token: str,
    ) -> LineageGraph:
        semantic_task = self.semantic_model_service.get_parsed_definition(
            workspace_id=request.semantic_model_workspace_id,
            semantic_model_id=request.semantic_model_id,
            access_token=fabric_access_token,
            definition_format="TMDL",
        )
        report_task = None
        if request.report_id:
            report_task = self.report_definition_service.get_normalized_definition(
                workspace_id=(
                    request.report_workspace_id or request.semantic_model_workspace_id
                ),
                report_id=request.report_id,
                access_token=fabric_access_token,
                definition_format=request.report_definition_format,
            )

        if report_task is None:
            semantic_model = await semantic_task
            report = None
        else:
            semantic_model, report = await asyncio.gather(
                semantic_task,
                report_task,
            )

        gateway_datasources, gateway_warnings = await self._gateway_datasources(
            include=request.include_gateway_sources,
            access_token=powerbi_access_token,
        )
        physical = PhysicalSourceDiscoveryService().discover(
            semantic_model,
            gateway_datasources=gateway_datasources,
        )
        physical.warnings.extend(gateway_warnings)

        report_lineage = None
        if report is not None:
            report_lineage = self.report_lineage_service.match(
                report=report,
                semantic_model=semantic_model,
                semantic_model_workspace_id=request.semantic_model_workspace_id,
            )

        return LineageGraphService().build(
            LineageGraphBuildRequest(
                semantic_model=semantic_model,
                physical_sources=physical,
                report_lineage=report_lineage,
            )
        )

    async def _gateway_datasources(
        self,
        *,
        include: bool,
        access_token: str,
    ) -> tuple[list[GatewayDatasource], list[PhysicalSourceWarning]]:
        if not include:
            return [], []
        try:
            gateways = await self.gateway_service.list_gateways(
                access_token=access_token,
            )
        except AppException as exc:
            return [], [self._gateway_warning(exc)]

        results = await asyncio.gather(
            *(
                self.gateway_service.list_datasources(
                    gateway_id=gateway.id,
                    access_token=access_token,
                )
                for gateway in gateways.gateways
            ),
            return_exceptions=True,
        )
        datasources = []
        warnings: list[PhysicalSourceWarning] = []
        for result in results:
            if isinstance(result, AppException):
                warnings.append(self._gateway_warning(result))
            elif isinstance(result, Exception):
                raise result
            else:
                datasources.extend(result.datasources)
        return datasources, warnings

    @staticmethod
    def _gateway_warning(exc: AppException) -> PhysicalSourceWarning:
        return PhysicalSourceWarning(
            code=exc.code,
            message=(
                "Gateway metadata could not be included; "
                "Power Query source discovery continued."
            ),
        )
