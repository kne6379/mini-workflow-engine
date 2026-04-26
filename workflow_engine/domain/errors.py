class WorkflowEngineError(Exception):
    code = "WORKFLOW_ENGINE_ERROR"


class WorkflowValidationError(WorkflowEngineError):
    code = "WORKFLOW_VALIDATION_ERROR"


class InputMappingError(WorkflowEngineError):
    code = "INPUT_MAPPING_ERROR"


class LLMOutputValidationError(WorkflowEngineError):
    code = "LLM_OUTPUT_VALIDATION_ERROR"


class ApprovalTimeoutError(WorkflowEngineError):
    code = "APPROVAL_TIMEOUT"
