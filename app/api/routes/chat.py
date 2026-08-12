from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_admin
from app.core.chat_logger import log_chat
from app.core.config import get_settings
from app.db.session import get_session
from app.models import Business, BusinessAdmin, ChatHeader, ChatRequest, Workspace, WorkspaceConfig
from app.schemas.rag import (
    ChatHeadersResponse,
    ChatHeaderItem,
    ChatRequest as ChatRequestSchema,
    ChatResponse as ChatResponseSchema,
    ChatThreadMessage,
    ChatThreadResponse,
    ChatUsage,
    CreateChatHeaderRequest,
    RenameChatHeaderRequest,
)
from app.services.chat_service import ChatService
from app.services.system_config_service import get_openai_api_key

router = APIRouter(prefix="/chat", tags=["Chat"])

WHISPER_TRANSCRIBE_MODEL = "whisper-1"
MAX_AUDIO_BYTES = 25 * 1024 * 1024


async def _transcribe_audio(
    audio_bytes: bytes,
    filename: str,
    content_type: str,
    openai_api_key: str,
) -> str:
    settings = get_settings()
    headers = {"Authorization": f"Bearer {openai_api_key}"}
    files = {
        "file": (filename or "voice-note.webm", audio_bytes, content_type or "audio/webm"),
    }
    data = {"model": WHISPER_TRANSCRIBE_MODEL}

    async with httpx.AsyncClient(base_url=settings.openai_base_url, timeout=120) as client:
        response = await client.post(
            "/audio/transcriptions",
            headers=headers,
            files=files,
            data=data,
        )

    if response.status_code >= 400:
        log_chat(
            "CHAT_ERROR",
            "Whisper transcription failed",
            step="transcribe",
            status_code=response.status_code,
            response_body=(response.text or "")[:500],
        )
        raise HTTPException(
            status_code=502,
            detail="Failed to transcribe audio with speech-to-text service.",
        )

    try:
        payload = response.json()
    except Exception as exc:  # noqa: BLE001
        log_chat("CHAT_ERROR", "Whisper response parse failed", step="transcribe", error=str(exc))
        raise HTTPException(status_code=502, detail="Invalid response from speech-to-text service.")

    return str(payload.get("text", "")).strip()


async def _resolve_business_workspace(
    session: AsyncSession,
    business_client_id: str,
    workspace_id: str,
) -> tuple[Business, Workspace, WorkspaceConfig]:
    business = (
        await session.execute(
            select(Business).where(Business.business_client_id == business_client_id)
        )
    ).scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    workspace = (
        await session.execute(
            select(Workspace).where(
                Workspace.business_id == business.id,
                Workspace.workspace_id == workspace_id,
            )
        )
    ).scalar_one_or_none()
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    config = (
        await session.execute(
            select(WorkspaceConfig).where(WorkspaceConfig.workspace_id == workspace.id)
        )
    ).scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Workspace config not found. Create or seed config for this workspace.")

    return business, workspace, config


@router.post("/generate", response_model=ChatResponseSchema)
async def generate_chat(
    payload: ChatRequestSchema,
    session: AsyncSession = Depends(get_session),
) -> ChatResponseSchema:
    log_chat(
        "CHAT_REQUEST_RECEIVED",
        "Chat /generate request received",
        business_client_id=payload.business_client_id,
        workspace_id=payload.workspace_id,
        user_id=payload.user_id,
        chat_id=payload.chat_id,
        query=payload.query[:200] if payload.query else "",
    )

    try:
        business, workspace, config = await _resolve_business_workspace(
            session,
            payload.business_client_id,
            payload.workspace_id,
        )
        config_prompt = (getattr(config, "prompt_engineering", None) or "").strip()
        prompt_engineering = (
            config_prompt
            or (payload.prompt_engineering or "").strip()
            or "You are a medical and nursing assistant. Answer only clinical and healthcare questions. Refuse unrelated topics."
        )

        request_images = payload.image_data_urls or (
            [payload.image_data_url] if payload.image_data_url else []
        )

        service = ChatService()
        answer, sources, usage, resolved_chat_id, resolved_title = await service.generate_response(
            session=session,
            business_id=business.id,
            workspace_id=workspace.id,
            user_id=payload.user_id,
            query=payload.query,
            prompt_engineering=prompt_engineering,
            config=config,
            override=payload.chat_config_override.model_dump() if payload.chat_config_override else None,
            chat_id=payload.chat_id,
            chat_title=payload.chat_title,
            image_data_urls=request_images,
        )

        return ChatResponseSchema(
            business_client_id=payload.business_client_id,
            workspace_id=payload.workspace_id,
            user_id=payload.user_id,
            query=payload.query,
            answer=answer,
            sources=sources,
            usage=ChatUsage(
                model=usage.get("model", config.chat_model_default),
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
            ),
            chat_id=resolved_chat_id,
            chat_title=resolved_title,
        )
    except HTTPException:
        raise
    except NoResultFound as e:
        log_chat("CHAT_ERROR", "NoResultFound in chat route", step="lookup", error=str(e), error_type="NoResultFound")
        raise HTTPException(status_code=404, detail="Resource not found (business, workspace, or config).")
    except Exception as e:
        log_chat("CHAT_ERROR", "Chat generate failed", step="generate", error=str(e), error_type=type(e).__name__)
        raise HTTPException(
            status_code=500,
            detail="Unable to generate a response right now. Please try again.",
        )


@router.post("/voice-generate")
async def voice_generate_chat(
    business_client_id: str = Form(...),
    workspace_id: str = Form(...),
    user_id: str = Form(...),
    chat_id: str | None = Form(None),
    chat_title: str | None = Form(None),
    prompt_engineering: str | None = Form(None),
    audio_file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
) -> dict:
    log_chat(
        "CHAT_VOICE_REQUEST_RECEIVED",
        "Chat /voice-generate request received",
        business_client_id=business_client_id,
        workspace_id=workspace_id,
        user_id=user_id,
        chat_id=chat_id,
        audio_content_type=audio_file.content_type,
    )

    try:
        audio_bytes = await audio_file.read()
        if not audio_bytes:
            raise HTTPException(status_code=422, detail="Uploaded audio file is empty.")
        if len(audio_bytes) > MAX_AUDIO_BYTES:
            raise HTTPException(status_code=413, detail="Audio file is too large (max 25MB).")

        openai_api_key = (await get_openai_api_key(session)) or get_settings().openai_api_key
        if not openai_api_key or not openai_api_key.strip():
            raise HTTPException(
                status_code=400,
                detail="OPENAI_API_KEY not configured. Set it in System configurations.",
            )

        transcript = await _transcribe_audio(
            audio_bytes,
            audio_file.filename or "voice-note.webm",
            audio_file.content_type or "audio/webm",
            openai_api_key.strip(),
        )

        if not transcript:
            raise HTTPException(
                status_code=422,
                detail="Could not detect any speech in the recording. Please try again.",
            )

        log_chat(
            "CHAT_VOICE_TRANSCRIBED",
            "Voice note transcribed",
            business_client_id=business_client_id,
            workspace_id=workspace_id,
            user_id=user_id,
            transcript=transcript[:200],
        )

        business, workspace, config = await _resolve_business_workspace(
            session,
            business_client_id,
            workspace_id,
        )
        config_prompt = (getattr(config, "prompt_engineering", None) or "").strip()
        resolved_prompt = (
            config_prompt
            or (prompt_engineering or "").strip()
            or "You are a medical and nursing assistant. Answer only clinical and healthcare questions. Refuse unrelated topics."
        )

        service = ChatService()
        answer, sources, usage, resolved_chat_id, resolved_title = await service.generate_response(
            session=session,
            business_id=business.id,
            workspace_id=workspace.id,
            user_id=user_id,
            query=transcript,
            prompt_engineering=resolved_prompt,
            config=config,
            override=None,
            chat_id=chat_id,
            chat_title=chat_title,
        )

        return {
            "business_client_id": business_client_id,
            "workspace_id": workspace_id,
            "user_id": user_id,
            "query": transcript,
            "transcript": transcript,
            "answer": answer,
            "sources": [source.model_dump() if hasattr(source, "model_dump") else source for source in sources],
            "usage": {
                "model": usage.get("model", config.chat_model_default),
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            },
            "chat_id": resolved_chat_id,
            "chat_title": resolved_title,
        }
    except HTTPException:
        raise
    except NoResultFound as e:
        log_chat("CHAT_ERROR", "NoResultFound in voice chat route", step="lookup", error=str(e), error_type="NoResultFound")
        raise HTTPException(status_code=404, detail="Resource not found (business, workspace, or config).")
    except Exception as e:
        log_chat("CHAT_ERROR", "Voice chat generate failed", step="voice_generate", error=str(e), error_type=type(e).__name__)
        raise HTTPException(
            status_code=500,
            detail="Unable to process your voice message right now. Please try again.",
        )


@router.get("/headers/me", response_model=ChatHeadersResponse)
async def get_my_chat_headers(
    session: AsyncSession = Depends(get_session),
    admin: BusinessAdmin = Depends(get_current_admin),
) -> ChatHeadersResponse:
    owner = (admin.email or "").strip().lower()
    headers = (
        await session.execute(
            select(ChatHeader)
            .where(
                ChatHeader.owner_user_id == owner,
                ChatHeader.deleted_at.is_(None),
            )
            .order_by(ChatHeader.updated_at.desc().nullslast(), ChatHeader.created_at.desc())
        )
    ).scalars().all()

    chats = [
        ChatHeaderItem(
            chat_id=header.chat_id,
            title=header.title or "New chat",
            user_id=header.owner_user_id,
            created_at=header.created_at.isoformat() if header.created_at else None,
            updated_at=header.updated_at.isoformat() if header.updated_at else None,
        )
        for header in headers
    ]

    return ChatHeadersResponse(user_id=owner, count=len(chats), chats=chats)


@router.post("/headers")
async def create_chat_header(
    payload: CreateChatHeaderRequest,
    session: AsyncSession = Depends(get_session),
    admin: BusinessAdmin = Depends(get_current_admin),
) -> dict:
    business, workspace, _ = await _resolve_business_workspace(
        session,
        payload.business_client_id,
        payload.workspace_id,
    )
    owner = (payload.user_id or admin.email or "").strip().lower()
    chat_id = (payload.chat_id or "").strip()
    if not chat_id:
        raise HTTPException(status_code=400, detail="chat_id is required")

    title = (payload.chat_title or "").strip() or "New chat"
    header = (
        await session.execute(
            select(ChatHeader).where(
                ChatHeader.owner_user_id == owner,
                ChatHeader.business_id == business.id,
                ChatHeader.workspace_id == workspace.id,
                ChatHeader.chat_id == chat_id,
            )
        )
    ).scalar_one_or_none()

    if header is None:
        header = ChatHeader(
            owner_user_id=owner,
            business_id=business.id,
            workspace_id=workspace.id,
            chat_id=chat_id,
            title=title[:80],
            deleted_at=None,
        )
        session.add(header)
    else:
        header.deleted_at = None
        if title and title.lower() != "new chat":
            header.title = title[:80]

    await session.commit()
    return {
        "status": "ok",
        "chat_id": header.chat_id,
        "title": header.title,
    }


@router.get("/threads/{chat_id}", response_model=ChatThreadResponse)
async def get_chat_thread(
    chat_id: str,
    session: AsyncSession = Depends(get_session),
    admin: BusinessAdmin = Depends(get_current_admin),
) -> ChatThreadResponse:
    owner = (admin.email or "").strip().lower()
    chat_id = (chat_id or "").strip()

    header = (
        await session.execute(
            select(ChatHeader).where(
                ChatHeader.owner_user_id == owner,
                ChatHeader.chat_id == chat_id,
                ChatHeader.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()

    # Legacy fallback: chats saved under a mismatched user_id still load for the
    # authenticated admin, then ownership is normalized for future requests.
    if header is None:
        header = (
            await session.execute(
                select(ChatHeader).where(
                    ChatHeader.chat_id == chat_id,
                    ChatHeader.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if header is not None and (header.owner_user_id or "").strip().lower() != owner:
            header.owner_user_id = owner
            await session.commit()

    if not header:
        raise HTTPException(status_code=404, detail="Chat not found")

    requests = (
        await session.execute(
            select(ChatRequest)
            .options(selectinload(ChatRequest.response))
            .where(ChatRequest.chat_header == chat_id)
            .order_by(ChatRequest.created_at.asc())
        )
    ).scalars().all()

    messages: list[ChatThreadMessage] = []
    for item in requests:
        messages.append(
            ChatThreadMessage(
                role="user",
                content=item.query_text or "",
                timestamp=item.created_at.isoformat() if item.created_at else None,
            )
        )
        if item.response:
            messages.append(
                ChatThreadMessage(
                    role="assistant",
                    content=item.response.answer_text or "",
                    timestamp=item.response.created_at.isoformat() if item.response.created_at else None,
                )
            )

    return ChatThreadResponse(
        chat_id=header.chat_id,
        title=header.title or "New chat",
        messages=messages,
    )


@router.patch("/headers/{chat_id}")
async def rename_chat_header(
    chat_id: str,
    payload: RenameChatHeaderRequest,
    session: AsyncSession = Depends(get_session),
    admin: BusinessAdmin = Depends(get_current_admin),
) -> dict:
    owner = (admin.email or "").strip().lower()
    chat_id = (chat_id or "").strip()
    title = (payload.title or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="title is required")

    header = (
        await session.execute(
            select(ChatHeader).where(
                ChatHeader.owner_user_id == owner,
                ChatHeader.chat_id == chat_id,
                ChatHeader.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()

    if header is None:
        header = (
            await session.execute(
                select(ChatHeader).where(
                    ChatHeader.chat_id == chat_id,
                    ChatHeader.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if header is not None:
            header.owner_user_id = owner

    if not header:
        raise HTTPException(status_code=404, detail="Chat header not found")

    header.title = title[:80]
    await session.commit()

    return {
        "status": "renamed",
        "chat_id": header.chat_id,
        "title": header.title,
    }


@router.delete("/headers/{chat_id}")
async def soft_delete_chat_header(
    chat_id: str,
    session: AsyncSession = Depends(get_session),
    admin: BusinessAdmin = Depends(get_current_admin),
) -> dict:
    owner = (admin.email or "").strip().lower()
    chat_id = (chat_id or "").strip()

    header = (
        await session.execute(
            select(ChatHeader).where(
                ChatHeader.owner_user_id == owner,
                ChatHeader.chat_id == chat_id,
                ChatHeader.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()

    if header is None:
        header = (
            await session.execute(
                select(ChatHeader).where(
                    ChatHeader.chat_id == chat_id,
                    ChatHeader.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()

    if not header:
        raise HTTPException(status_code=404, detail="Chat header not found")

    header.deleted_at = datetime.now(timezone.utc)
    if (header.owner_user_id or "").strip().lower() != owner:
        header.owner_user_id = owner
    await session.commit()

    return {"status": "deleted", "chat_id": chat_id, "soft_deleted": True}
