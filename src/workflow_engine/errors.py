class WorkflowEngineError(Exception):
    code = "WORKFLOW_ENGINE_ERROR"


class WorkflowValidationError(WorkflowEngineError):
    code = "WORKFLOW_VALIDATION_ERROR"


class InputMappingError(WorkflowEngineError):
    code = "INPUT_MAPPING_ERROR"
