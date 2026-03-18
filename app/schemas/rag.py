from pydantic import BaseModel, Field


class RetrievalRequest(BaseModel):
    business_client_id: str = Field(..., example="acme")
    workspace_id: str = Field(..., example="main")
    user_id: str = Field(..., example="u123")
    query: str = Field(..., example="What are symptoms of ...?")
    top_k: int | None = Field(None, example=5)


class RetrievedChunk(BaseModel):
    chunk_id: str
    document_id: str
    filename: str
    page: int | None
    score: float
    content: str


class RetrievalResponse(BaseModel):
    business_client_id: str
    workspace_id: str
    user_id: str
    query: str
    retrieved_chunks: list[RetrievedChunk]


class ChatConfigOverride(BaseModel):
    model: str | None = Field(None, example="gpt-4.1-mini")
    temperature: float | None = Field(None, example=0.2)
    max_tokens: int | None = Field(None, example=600)


class ChatRequest(BaseModel):
    business_client_id: str = Field(..., example="acme")
    workspace_id: str = Field(..., example="main")
    user_id: str = Field(..., example="user@example.com")
    query: str = Field(..., example="User question here")
    chat_id: str | None = Field(None, example="f3f1893f-267e-4f7a-a012-4f84136f12de")
    chat_title: str | None = Field(None, example="Symptoms follow up")
    prompt_engineering: str | None = Field(
        None,
        example="You are a medical assistant. Provide concise answers.",
        description="Override system prompt. If omitted, uses workspace config prompt.",
    )
    chat_config_override: ChatConfigOverride | None = None


class ChatSource(BaseModel):
    document_id: str
    filename: str
    page: int | None
    chunk_id: str
    snippet: str


class ChatUsage(BaseModel):
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatResponse(BaseModel):
    business_client_id: str
    workspace_id: str
    user_id: str
    query: str
    answer: str
    sources: list[ChatSource]
    usage: ChatUsage


class ChatHistoryItem(BaseModel):
    chat_id: str
    title: str
    user_id: str
    created_at: str
    updated_at: str | None = None


class ChatHistoryResponse(BaseModel):
    user_id: str
    count: int
    chats: list[ChatHistoryItem]
