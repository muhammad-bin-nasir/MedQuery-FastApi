import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import NoResultFound

from app.api.deps import ensure_rag_access, get_current_admin, require_admin
from app.core.chat_logger import log_chat
from app.core.limiter import get_user_key, limiter
from app.core.security import normalize_email
from app.db.session import get_session
from app.models import (
    Business,
    BusinessAdmin,
    ChatHeader,
    ChatRequest as ChatRequestModel,
    ChatResponse as ChatResponseModel,
    Workspace,
    WorkspaceConfig,
)
from app.schemas.rag import ChatHistoryItem, ChatHistoryResponse, ChatRequest, ChatResponse, ChatUsage
from app.services.chat_service import ChatService

router = APIRouter(prefix="/chat", tags=["Chat"])


def _map_chat_headers(headers: list[ChatHeader]) -> list[ChatHistoryItem]:
    return [
        ChatHistoryItem(
            chat_id=header.chat_id,
            title=header.title,
            user_id=header.owner_user_id or (str(header.owner_user_uuid) if header.owner_user_uuid else ""),
            created_at=header.created_at.isoformat(),
            updated_at=header.updated_at.isoformat() if header.updated_at else None,
        )
        for header in headers
    ]


@router.delete("/headers/{chat_id}")
async def delete_chat_header(
    chat_id: str,
    session: AsyncSession = Depends(get_session),
    admin: BusinessAdmin = Depends(get_current_admin),
) -> dict:
    """Delete one chat thread header and its linked request and response records."""
    owner_user_id = admin.email
    owner_user_uuid = admin.id
    stmt = select(ChatHeader).where(
        or_(
            ChatHeader.owner_user_uuid == owner_user_uuid,
            and_(ChatHeader.owner_user_uuid.is_(None), ChatHeader.owner_user_id == owner_user_id),
        ),
        ChatHeader.chat_id == chat_id,
    )
    header = (await session.execute(stmt)).scalar_one_or_none()
    if not header:
        raise HTTPException(status_code=404, detail="Chat header not found")

    request_ids = (
        (
            await session.execute(
                select(ChatRequestModel.id).where(
                    or_(
                        ChatRequestModel.user_uuid == owner_user_uuid,
                        and_(ChatRequestModel.user_uuid.is_(None), ChatRequestModel.user_id == owner_user_id),
                    ),
                    ChatRequestModel.business_id == header.business_id,
                    ChatRequestModel.workspace_id == header.workspace_id,
                    ChatRequestModel.chat_header == chat_id,
                )
            )
        )
        .scalars()
        .all()
    )

    deleted_responses = 0
    if request_ids:
        response_delete_result = await session.execute(
            delete(ChatResponseModel).where(ChatResponseModel.request_id.in_(request_ids))
        )
        deleted_responses = response_delete_result.rowcount or 0

        await session.execute(delete(ChatRequestModel).where(ChatRequestModel.id.in_(request_ids)))

    await session.delete(header)
    await session.commit()

    log_chat(
        "CHAT_HEADER_DELETED",
        "Chat header deleted",
        chat_id=chat_id,
        owner_user_id=owner_user_id,
        requester_admin_id=str(admin.id),
        requester_role=admin.role,
        deleted_requests=len(request_ids),
        deleted_responses=deleted_responses,
    )

    return {"status": "deleted", "chat_id": chat_id}


@router.get("/headers/me", response_model=ChatHistoryResponse)
async def get_my_chat_headers(
    session: AsyncSession = Depends(get_session),
    admin: BusinessAdmin = Depends(get_current_admin),
) -> ChatHistoryResponse:
    """List chat headers for the current user or fallback admin account."""
    owner_user_id = admin.email
    owner_user_uuid = admin.id
    stmt = (
        select(ChatHeader)
        .where(
            or_(
                ChatHeader.owner_user_uuid == owner_user_uuid,
                and_(ChatHeader.owner_user_uuid.is_(None), ChatHeader.owner_user_id == owner_user_id),
            )
        )
        .order_by(ChatHeader.updated_at.desc(), ChatHeader.created_at.desc())
    )
    headers = (await session.execute(stmt)).scalars().all()
    chats = _map_chat_headers(headers)
    return ChatHistoryResponse(user_id=owner_user_id, count=len(chats), chats=chats)


@router.get("/history/{user_id}", response_model=ChatHistoryResponse)
async def get_user_chat_history(
    user_id: str,
    session: AsyncSession = Depends(get_session),
    admin: BusinessAdmin = Depends(require_admin),
) -> ChatHistoryResponse:
    """Fetch chat history for a specific user email identifier."""
    requested_owner = normalize_email(user_id)
    stmt = (
        select(ChatHeader)
        .where(ChatHeader.owner_user_id == requested_owner)
        .order_by(ChatHeader.updated_at.desc(), ChatHeader.created_at.desc())
    )
    headers = (await session.execute(stmt)).scalars().all()
    chats = _map_chat_headers(headers)

    log_chat(
        "CHAT_HISTORY_FETCHED",
        "Admin fetched chat history by user_id",
        requested_user_id=requested_owner,
        requester_admin_id=str(admin.id),
        requester_role=admin.role,
        count=len(chats),
    )

    return ChatHistoryResponse(user_id=requested_owner, count=len(chats), chats=chats)


@router.post("/generate", response_model=ChatResponse)
@limiter.limit("30/minute", key_func=get_user_key)
async def generate_chat(
    request: Request,
    payload: ChatRequest,
    session: AsyncSession = Depends(get_session),
    admin: BusinessAdmin = Depends(get_current_admin),
) -> ChatResponse:
    """Generate a grounded answer for a user prompt using the indexed workspace knowledge base."""
    effective_user_id = admin.email
    effective_user_uuid = admin.id
    log_chat(
        "CHAT_REQUEST_RECEIVED",
        "Chat /generate request received",
        business_client_id=payload.business_client_id,
        workspace_id=payload.workspace_id,
        user_id=effective_user_id,
        query=payload.query[:200] if payload.query else "",
    )

    try:
        business = (
            await session.execute(
                select(Business).where(Business.business_client_id == payload.business_client_id)
            )
        ).scalar_one_or_none()
        if not business:
            log_chat("CHAT_ERROR", "Business not found", step="business_lookup", business_client_id=payload.business_client_id)
            raise HTTPException(status_code=404, detail="Business not found")
        if admin.role == "admin" and business.admin_id != admin.id:
            log_chat("CHAT_ERROR", "Admin not owner of business", step="business_access", business_id=str(business.id))
            raise HTTPException(status_code=403, detail="Not allowed")
        log_chat("CHAT_BUSINESS_FOUND", "Business resolved", business_id=str(business.id))

        workspace = (
            await session.execute(
                select(Workspace).where(
                    Workspace.business_id == business.id,
                    Workspace.workspace_id == payload.workspace_id,
                )
            )
        ).scalar_one_or_none()
        if not workspace:
            log_chat("CHAT_ERROR", "Workspace not found", step="workspace_lookup", workspace_id=payload.workspace_id)
            raise HTTPException(status_code=404, detail="Workspace not found")
        ensure_rag_access(admin, business_id=business.id, workspace_id=workspace.id)
        log_chat("CHAT_WORKSPACE_FOUND", "Workspace resolved", workspace_id=str(workspace.id))

        config = (
            await session.execute(
                select(WorkspaceConfig).where(WorkspaceConfig.workspace_id == workspace.id)
            )
        ).scalar_one_or_none()
        if not config:
            log_chat("CHAT_ERROR", "Workspace config not found", step="config_lookup", workspace_id=str(workspace.id))
            raise HTTPException(status_code=404, detail="Workspace config not found. Create or seed config for this workspace.")
        config_prompt = (getattr(config, "prompt_engineering", None) or "").strip()
        log_chat(
            "CHAT_CONFIG_FOUND",
            "Workspace config loaded",
            embedding_model=config.embedding_model,
            chat_model=config.chat_model_default,
            prompt_from_db_len=len(config_prompt),
        )

        # Workspace config (DB) is primary; payload is override only when config is empty
        prompt_engineering = (
            config_prompt
            or (payload.prompt_engineering or "").strip()
            or "You are a medical assistant. Provide concise answers based on the context."
        )

        service = ChatService()
        answer, sources, usage = await service.generate_response(
            session=session,
            business_id=business.id,
            workspace_id=workspace.id,
            user_id=effective_user_id,
            user_uuid=effective_user_uuid,
            chat_header=payload.chat_id,
            query=payload.query,
            prompt_engineering=prompt_engineering,
            config=config,
            override=payload.chat_config_override.model_dump() if payload.chat_config_override else None,
        )

        if payload.chat_id:
            header_stmt = select(ChatHeader).where(
                ChatHeader.owner_user_uuid == effective_user_uuid,
                ChatHeader.business_id == business.id,
                ChatHeader.workspace_id == workspace.id,
                ChatHeader.chat_id == payload.chat_id,
            )
            header = (await session.execute(header_stmt)).scalar_one_or_none()
            fallback_title = (payload.query or "").strip().split("\n", 1)[0][:80] or "New chat"
            title = (payload.chat_title or "").strip() or fallback_title

            if header:
                header.title = title
            else:
                session.add(
                    ChatHeader(
                        owner_user_id=effective_user_id,
                        owner_user_uuid=effective_user_uuid,
                        business_id=business.id,
                        workspace_id=workspace.id,
                        chat_id=payload.chat_id,
                        title=title,
                    )
                )
            await session.commit()

        return ChatResponse(
            business_client_id=payload.business_client_id,
            workspace_id=payload.workspace_id,
            user_id=effective_user_id,
            query=payload.query,
            answer=answer,
            sources=sources,
            usage=ChatUsage(
                model=usage.get("model", config.chat_model_default),
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
            ),
        )
    except HTTPException:
        raise
    except NoResultFound as e:
        log_chat("CHAT_ERROR", "NoResultFound in chat route", step="lookup", error=str(e), error_type="NoResultFound")
        raise HTTPException(status_code=404, detail="Resource not found (business, workspace, or config).")
    except Exception as e:
        log_chat("CHAT_ERROR", "Chat generate failed", step="generate", error=str(e), error_type=type(e).__name__)
        raise HTTPException(status_code=500, detail=f"Chat failed: {str(e)}")


@router.post("/stream")
@limiter.limit("30/minute", key_func=get_user_key)
async def stream_chat(
    request: Request,
    payload: ChatRequest,
    session: AsyncSession = Depends(get_session),
    admin: BusinessAdmin = Depends(get_current_admin),
) -> StreamingResponse:
    """Stream a generated answer as server-sent events for live chat UIs.

    Token events:  ``data: {"token": "..."}``
    Done event:    ``data: {"type": "done", "sources": [...]}``
    Error event:   ``data: {"type": "error", "message": "..."}``
    """
    effective_user_id = admin.email
    effective_user_uuid = admin.id

    # ── Validate business / workspace / config before opening the stream ──
    try:
        business = (
            await session.execute(
                select(Business).where(Business.business_client_id == payload.business_client_id)
            )
        ).scalar_one_or_none()
        if not business:
            raise HTTPException(status_code=404, detail="Business not found")
        if admin.role == "admin" and business.admin_id != admin.id:
            raise HTTPException(status_code=403, detail="Not allowed")

        workspace = (
            await session.execute(
                select(Workspace).where(
                    Workspace.business_id == business.id,
                    Workspace.workspace_id == payload.workspace_id,
                )
            )
        ).scalar_one_or_none()
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")
        ensure_rag_access(admin, business_id=business.id, workspace_id=workspace.id)

        config = (
            await session.execute(
                select(WorkspaceConfig).where(WorkspaceConfig.workspace_id == workspace.id)
            )
        ).scalar_one_or_none()
        if not config:
            raise HTTPException(status_code=404, detail="Workspace config not found.")

        config_prompt = (getattr(config, "prompt_engineering", None) or "").strip()
        prompt_engineering = (
            config_prompt
            or (payload.prompt_engineering or "").strip()
            or "You are a medical assistant. Provide concise answers based on the context."
        )
    except HTTPException:
        raise
    except Exception as e:
        log_chat("CHAT_STREAM_ERROR", "Stream chat setup failed", error=str(e), error_type=type(e).__name__)
        raise HTTPException(status_code=500, detail=f"Stream chat failed: {str(e)}")

    service = ChatService()

    async def event_stream():
        try:
            # Send a start marker
            import json as _json
            yield f"data: {_json.dumps({'type': 'start'})}\n\n"
            
            token_count = 0
            async for chunk in service.generate_response_stream(
                session=session,
                business_id=business.id,
                workspace_id=workspace.id,
                user_id=effective_user_id,
                user_uuid=effective_user_uuid,
                chat_header=payload.chat_id,
                chat_title=payload.chat_title,
                query=payload.query,
                prompt_engineering=prompt_engineering,
                config=config,
                override=payload.chat_config_override.model_dump() if payload.chat_config_override else None,
            ):
                yield chunk
                token_count += 1
                await asyncio.sleep(0)  # Yield control immediately
        except Exception as exc:
            log_chat("CHAT_STREAM_ERROR", "Streaming chunk failed", error=str(exc), error_type=type(exc).__name__)
            import json as _json
            yield f"data: {_json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
            "Transfer-Encoding": "chunked",
        },
    )


@router.get("/test-stream")
async def test_stream() -> StreamingResponse:
    """Test endpoint to verify SSE streaming works at all."""
    async def test_generator():
        for i in range(10):
            yield f"data: {json.dumps({'token': f'TOKEN_{i}', 'num': i})}\n\n"
            await asyncio.sleep(0.1)
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
    
    return StreamingResponse(
        test_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
