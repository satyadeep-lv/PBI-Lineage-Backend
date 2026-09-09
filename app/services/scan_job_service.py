import asyncio
import logging
from uuid import uuid4

from app.schemas.lineage_graph import LineageGraph
from app.schemas.scan_job import (
    LineageScanJob,
    LineageScanJobRequest,
    LiveLineageScanRequest,
)
from app.services.lineage_graph_service import LineageGraphService
from app.services.lineage_store_service import LineageStoreService
from app.services.lineage_validation_service import LineageValidationService
from app.services.live_lineage_scan_service import LiveLineageScanService

logger = logging.getLogger(__name__)


class LineageScanJobManager:
    def __init__(
        self,
        store: LineageStoreService,
        *,
        max_concurrency: int = 2,
    ) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be positive.")
        self.store = store
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.tasks: set[asyncio.Task[None]] = set()
        self.live_scan_service = LiveLineageScanService()
        self.store.repository.fail_interrupted_jobs()

    async def submit(self, request: LineageScanJobRequest) -> LineageScanJob:
        job_id = str(uuid4())
        job = await asyncio.to_thread(
            self.store.repository.create_job,
            job_id=job_id,
            request_payload=request.model_dump(mode="json"),
        )
        task = asyncio.create_task(self._execute(job_id, request))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return job

    async def submit_live(
        self,
        request: LiveLineageScanRequest,
        *,
        fabric_access_token: str,
        powerbi_access_token: str,
    ) -> LineageScanJob:
        job_id = str(uuid4())
        job = await asyncio.to_thread(
            self.store.repository.create_job,
            job_id=job_id,
            request_payload={
                "scan_type": "live",
                "request": request.model_dump(mode="json"),
            },
        )
        task = asyncio.create_task(
            self._execute_live(
                job_id,
                request,
                fabric_access_token=fabric_access_token,
                powerbi_access_token=powerbi_access_token,
            )
        )
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return job

    async def get(self, job_id: str) -> LineageScanJob | None:
        return await asyncio.to_thread(self.store.repository.get_job, job_id)

    async def _execute(
        self,
        job_id: str,
        request: LineageScanJobRequest,
    ) -> None:
        async with self.semaphore:
            await asyncio.to_thread(
                self.store.repository.update_job,
                job_id,
                status="running",
            )
            try:
                graph = await asyncio.to_thread(
                    LineageGraphService().build,
                    request.graph,
                )
                await self._store_result(job_id, graph)
            except Exception as exc:  # noqa: BLE001 - background job boundary
                await self._fail_job(job_id, exc)

    async def _execute_live(
        self,
        job_id: str,
        request: LiveLineageScanRequest,
        *,
        fabric_access_token: str,
        powerbi_access_token: str,
    ) -> None:
        async with self.semaphore:
            await asyncio.to_thread(
                self.store.repository.update_job,
                job_id,
                status="running",
            )
            try:
                graph = await self.live_scan_service.build_graph(
                    request,
                    fabric_access_token=fabric_access_token,
                    powerbi_access_token=powerbi_access_token,
                )
                await self._store_result(job_id, graph)
            except Exception as exc:  # noqa: BLE001 - background job boundary
                await self._fail_job(job_id, exc)

    async def _store_result(self, job_id: str, graph: LineageGraph) -> None:
        validation = await asyncio.to_thread(
            LineageValidationService().validate,
            graph,
        )
        if not validation.valid:
            raise ValueError("Generated lineage graph failed validation.")
        stored = await asyncio.to_thread(self.store.save, graph)
        await asyncio.to_thread(
            self.store.repository.update_job,
            job_id,
            status="succeeded",
            result=stored.metadata,
        )

    async def _fail_job(self, job_id: str, exc: Exception) -> None:
        logger.exception(
            "lineage_scan_job_failed",
            extra={
                "job_id": job_id,
                "exception_type": type(exc).__name__,
            },
        )
        await asyncio.to_thread(
            self.store.repository.update_job,
            job_id,
            status="failed",
            error_code="LINEAGE_SCAN_FAILED",
            error_message="The lineage scan could not be completed.",
        )
