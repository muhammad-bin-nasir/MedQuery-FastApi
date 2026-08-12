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
    user_id: str = Field(..., example="u123")
    query: str = Field(..., example="User question here")
    chat_id: str | None = Field(None, example="chat-uuid")
    chat_title: str | None = Field(None, example="NCLEX study tips")
    prompt_engineering: str | None = Field(
        None,
        example="You are a medical assistant. Provide concise answers.",
        description="Override system prompt. If omitted, uses workspace config prompt.",
    )
    image_data_url: str | None = Field(
        None,
        description="Single base64 image data URL (legacy/first image).",
    )
    image_data_urls: list[str] | None = Field(
        None,
        description="Up to 5 base64 image data URLs to analyze with the question.",
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
    chat_id: str | None = None
    chat_title: str | None = None


class ChatHeaderItem(BaseModel):
    chat_id: str
    title: str
    user_id: str
    created_at: str | None = None
    updated_at: str | None = None


class ChatHeadersResponse(BaseModel):
    user_id: str
    count: int
    chats: list[ChatHeaderItem]


class ChatThreadMessage(BaseModel):
    role: str
    content: str
    timestamp: str | None = None


class ChatThreadResponse(BaseModel):
    chat_id: str
    title: str
    messages: list[ChatThreadMessage]


class CreateChatHeaderRequest(BaseModel):
    business_client_id: str
    workspace_id: str
    user_id: str
    chat_id: str
    chat_title: str | None = None


class RenameChatHeaderRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=80, example="NCLEX study tips")
