from workflow_engine.domain.run import WorkflowRun
from workflow_engine.engine.ports import RunStore


class RunNotFoundError(Exception):
    pass


class RunStoreAdapter(RunStore):
    def __init__(self):
        self._runs: dict[str, WorkflowRun] = {}
        self._runs_by_inquiry: dict[str, str] = {}

    def save(self, run: WorkflowRun) -> WorkflowRun:
        self._runs[run.run_id] = run
        inquiry_id = run.context.get("input", {}).get("inquiry_id")
        if inquiry_id is not None:
            self._runs_by_inquiry[inquiry_id] = run.run_id
        return run

    def get(self, run_id: str) -> WorkflowRun:
        try:
            return self._runs[run_id]
        except KeyError as exc:
            raise RunNotFoundError(run_id) from exc

    def list_runs(self) -> list[WorkflowRun]:
        return list(self._runs.values())

    def find_by_inquiry(self, inquiry_id: str) -> WorkflowRun | None:
        run_id = self._runs_by_inquiry.get(inquiry_id)
        if run_id is None:
            return None
        return self._runs.get(run_id)
