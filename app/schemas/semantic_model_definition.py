from pydantic import (
    BaseModel,
    Field,
)


class SemanticModelDefinitionPart(BaseModel):
    path: str
    payload: str

    payload_type: str = Field(
        serialization_alias="payloadType",
    )


class SemanticModelDefinition(BaseModel):
    format: str | None = None

    parts: list[SemanticModelDefinitionPart]


class SemanticModelDefinitionResponse(BaseModel):
    workspace_id: str
    semantic_model_id: str

    definition: SemanticModelDefinition
