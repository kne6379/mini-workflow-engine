from workflow_engine.domain import WorkflowRun


class RunNotFoundError(Exception):
    pass


class InMemoryRunStore:
    def __init__(self):
        self._runs: dict[str, WorkflowRun] = {}

    def save(self, run: WorkflowRun) -> WorkflowRun:
        self._runs[run.run_id] = run
        return run

    def get(self, run_id: str) -> WorkflowRun:
        try:
            return self._runs[run_id]
        except KeyError as exc:
            raise RunNotFoundError(run_id) from exc

    def list_runs(self) -> list[WorkflowRun]:
        return list(self._runs.values())
