from pathlib import Path

import yaml

from workflow_engine.domain.workflow import WorkflowDefinition


def load_workflow(path: Path) -> WorkflowDefinition:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return WorkflowDefinition.model_validate(raw)
