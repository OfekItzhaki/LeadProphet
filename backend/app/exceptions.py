class PipelineError(Exception):
    def __init__(self, detail: str, lead_id: str | None = None):
        self.detail = detail
        self.lead_id = lead_id
        super().__init__(detail)
