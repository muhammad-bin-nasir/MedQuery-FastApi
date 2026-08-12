import json
import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.chat_logger import log_chat
from app.core.config import get_settings
from app.models import ChatHeader, ChatRequest, ChatResponse, WorkspaceConfig
from app.services.embedding_service import EmbeddingService
from app.services.retrieval_service import retrieve_chunks
from app.services.system_config_service import get_openai_api_key

PROMPT_PREVIEW_MAX = 800
ANSWER_PREVIEW_MAX = 500

# How many previous question/answer pairs of the same chat are replayed to the model
# so follow-up questions ("what is the second one?") keep their meaning.
MAX_HISTORY_TURNS = 6
HISTORY_ANSWER_MAX_CHARS = 1200

DOMAIN_GUARDRAIL = """
You are NursingAI, a medical and nursing assistant only.

Hard rules:
1. Answer ONLY questions about medicine, nursing, clinical care, patient safety, pharmacology, anatomy/physiology, diagnostics, treatments, medical education (e.g. NCLEX), or related healthcare topics.
2. If the question is unrelated to medicine/nursing/healthcare (for example geography, politics, sports, general trivia, coding, entertainment, personal advice unrelated to health), do NOT answer it.
3. For out-of-scope questions, reply briefly with something like: "I can only help with medical and nursing questions. Please ask a clinical or healthcare-related question."
4. Prefer the provided CONTEXT when it is relevant. If CONTEXT is empty or not useful, you may still answer medical/nursing questions carefully from established clinical knowledge, and say when information may be incomplete.
5. Do not invent citations. If you are unsure clinically, say so and recommend consulting a licensed clinician when appropriate.
6. Keep answers professional, concise, and clinically useful.

Images:
- The user may attach one or more images with a question. If images are attached and the topic is medical/nursing/healthcare (for example a wound, rash, X-ray, ECG, chart, medication label, or study material), analyze them and describe relevant clinical findings.
- Always note that visual assessment is not a diagnosis and recommend in-person evaluation by a licensed clinician when appropriate.
- If an attached image is clearly non-medical, say it is outside your scope.

Conversation continuity:
- The messages before the current question are the earlier turns of this same conversation. Use them.
- Short follow-ups ("what is the second one?", "why?", "and in children?", "explain more") refer to the immediately preceding medical topic. Resolve them against that topic and answer normally.
- Never treat a follow-up to a medical topic as out of scope. Only refuse when the underlying subject itself is non-medical.
- If a follow-up is genuinely ambiguous, ask one short clarifying question instead of refusing.
""".strip()


def build_chat_title(query: str, fallback: str = "New chat") -> str:
    normalized = " ".join(str(query or "").split()).strip()
    if not normalized:
        return fallback
    return normalized[:80]


class ChatService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.embedding_service = EmbeddingService()

    async def _load_recent_turns(
        self,
        session: AsyncSession,
        chat_id: str | None,
        limit: int = MAX_HISTORY_TURNS,
    ) -> list[tuple[str, str]]:
        """Return up to `limit` most recent (question, answer) pairs for a chat, oldest first."""
        resolved_chat_id = (chat_id or "").strip()
        if not resolved_chat_id:
            return []

        rows = (
            await session.execute(
                select(ChatRequest)
                .options(selectinload(ChatRequest.response))
                .where(ChatRequest.chat_header == resolved_chat_id)
                .order_by(ChatRequest.created_at.desc())
                .limit(limit)
            )
        ).scalars().all()

        turns: list[tuple[str, str]] = []
        for row in reversed(rows):
            question = (row.query_text or "").strip()
            answer = (row.response.answer_text or "").strip() if row.response else ""
            if question and answer:
                turns.append((question, answer[:HISTORY_ANSWER_MAX_CHARS]))

        return turns

    async def generate_response(
        self,
        session: AsyncSession,
        business_id: uuid.UUID,
        workspace_id: uuid.UUID,
        user_id: str,
        query: str,
        prompt_engineering: str,
        config: WorkspaceConfig,
        override: dict | None = None,
        chat_id: str | None = None,
        chat_title: str | None = None,
        image_data_urls: list[str] | None = None,
    ) -> tuple[str, list[dict], dict, str | None, str | None]:
        log_chat(
            "CHAT_QUERY_RECEIVED",
            "Query received in system",
            business_id=str(business_id),
            workspace_id=str(workspace_id),
            user_id=user_id,
            query=query,
            query_word_count=len(query.split()),
        )

        openai_api_key = (await get_openai_api_key(session)) or self.settings.openai_api_key

        history_turns = await self._load_recent_turns(session, chat_id)
        log_chat(
            "CHAT_HISTORY_LOADED",
            f"Loaded {len(history_turns)} previous turns for context",
            chat_id=chat_id,
            turn_count=len(history_turns),
        )

        # A short follow-up ("what is the second one?") retrieves poorly on its own,
        # so the previous question is prepended purely for the vector search.
        retrieval_query = query
        if history_turns:
            previous_question = history_turns[-1][0]
            retrieval_query = f"{previous_question}\n{query}"

        chunks = []
        embedding = None

        try:
            log_chat("CHAT_EMBEDDING_START", "Creating query embedding", embedding_model=config.embedding_model, use_local=config.use_local_embeddings)
            embedding = (await self.embedding_service.embed_texts(
                [retrieval_query],
                config.embedding_model,
                use_local=config.use_local_embeddings,
                openai_api_key=openai_api_key,
            ))[0]
            log_chat(
                "CHAT_EMBEDDING_DONE",
                "Query vector created",
                vector_dim=len(embedding),
                vector_preview=embedding[:8],
            )
        except Exception as e:
            log_chat("CHAT_ERROR", f"Step failed: embedding", step="embedding", error=str(e), error_type=type(e).__name__)
            # Degrade gracefully: continue chat without RAG retrieval when embeddings fail.
            chunks = []
            embedding = None

        if embedding is not None:
            try:
                log_chat("CHAT_RETRIEVAL_START", "Searching RAG for matching chunks", top_k=config.top_k, similarity_threshold=config.similarity_threshold)
                chunks = await retrieve_chunks(
                    session=session,
                    business_id=business_id,
                    workspace_id=workspace_id,
                    query_embedding=embedding,
                    top_k=config.top_k,
                    similarity_threshold=config.similarity_threshold,
                )
                chunk_ids = [str(c.id) for c, _, _ in chunks]
                chunk_summaries = [{"chunk_id": str(c.id), "filename": fn, "page": c.page_number, "distance": float(dist)} for c, fn, dist in chunks]
                log_chat(
                    "CHAT_RETRIEVAL_DONE",
                    f"Matched {len(chunks)} chunks",
                    chunk_count=len(chunks),
                    chunk_ids=chunk_ids,
                    chunks_matched=chunk_summaries,
                )
            except Exception as e:
                log_chat("CHAT_ERROR", f"Step failed: retrieval", step="retrieval", error=str(e), error_type=type(e).__name__)
                # Degrade gracefully: continue chat without RAG retrieval when lookup fails.
                chunks = []
        else:
            log_chat(
                "CHAT_RETRIEVAL_SKIPPED",
                "Skipped retrieval because embedding generation failed; answering without document context.",
            )

        context = "\n\n".join([chunk.content for chunk, _, _ in chunks])
        workspace_prompt = (prompt_engineering or "").strip()
        system_prompt = DOMAIN_GUARDRAIL
        if workspace_prompt:
            system_prompt = f"{DOMAIN_GUARDRAIL}\n\nAdditional workspace instructions:\n{workspace_prompt}"

        context_block = context if context.strip() else "(No matching document context was retrieved for this question.)"
        user_content = (
            f"CONTEXT:\n{context_block}\n\n"
            f"QUESTION:\n{query}\n\n"
            "Instructions for this turn: Treat this as a continuation of the conversation above. "
            "If the QUESTION is a short follow-up, resolve it against the previous topic and answer it. "
            "Only refuse when the underlying subject is not medical/nursing/healthcare related. "
            "Use CONTEXT when relevant."
        )
        clean_images = [
            url for url in (image_data_urls or [])
            if isinstance(url, str) and url.strip().startswith("data:image/")
        ][:5]

        messages = [{"role": "system", "content": system_prompt}]
        for previous_question, previous_answer in history_turns:
            messages.append({"role": "user", "content": previous_question})
            messages.append({"role": "assistant", "content": previous_answer})

        if clean_images:
            current_content = [{"type": "text", "text": user_content}]
            for image_url in clean_images:
                current_content.append({
                    "type": "image_url",
                    "image_url": {"url": image_url, "detail": "auto"},
                })
            messages.append({"role": "user", "content": current_content})
        else:
            messages.append({"role": "user", "content": user_content})
        full_prompt_preview = f"[SYSTEM]\n{system_prompt[:PROMPT_PREVIEW_MAX]}{'...' if len(system_prompt) > PROMPT_PREVIEW_MAX else ''}\n[USER]\n{user_content[:PROMPT_PREVIEW_MAX]}{'...' if len(user_content) > PROMPT_PREVIEW_MAX else ''}"
        log_chat(
            "CHAT_PROMPT_BUILT",
            "Final prompt assembled for ChatGPT API",
            system_prompt_len=len(system_prompt),
            context_len=len(context),
            user_content_len=len(user_content),
            history_turns=len(history_turns),
            image_count=len(clean_images),
            prompt_preview=full_prompt_preview,
        )

        model = (override.get("model") or config.chat_model_default) if override else config.chat_model_default
        model = model or self.settings.default_chat_model
        temperature = (
            (override.get("temperature") if override and "temperature" in override else config.chat_temperature_default)
            if override
            else config.chat_temperature_default
        )
        if temperature is None:
            temperature = config.chat_temperature_default
        max_tokens = (
            (override.get("max_tokens") if override and "max_tokens" in override else config.chat_max_tokens_default)
            if override
            else config.chat_max_tokens_default
        )
        if max_tokens is None:
            max_tokens = config.chat_max_tokens_default

        try:
            request_content_len = sum(
                len(m["content"]) if isinstance(m.get("content"), str) else 0
                for m in messages
            )
            log_chat("CHAT_OPENAI_CALL", f"Calling ChatGPT API (model={model})", model=model, temperature=temperature, max_tokens=max_tokens, message_count=len(messages), request_content_len=request_content_len)
            response = await self._call_openai(messages, model, temperature, max_tokens, openai_api_key=openai_api_key)
        except Exception as e:
            log_chat("CHAT_ERROR", "Step failed: OpenAI API call", step="openai_call", error=str(e), error_type=type(e).__name__)
            raise

        answer = response["choices"][0]["message"]["content"]
        usage = response.get("usage", {})
        log_chat(
            "CHAT_OPENAI_RESPONSE",
            "GPT response received",
            answer_preview=answer[:ANSWER_PREVIEW_MAX] + ("..." if len(answer) > ANSWER_PREVIEW_MAX else ""),
            full_answer=answer,
            answer_len=len(answer),
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
            raw_response=json.dumps(response, ensure_ascii=False),
        )

        sources = [
            {
                "document_id": str(chunk.document_id),
                "filename": filename,
                "page": chunk.page_number,
                "chunk_id": str(chunk.id),
                "snippet": chunk.content[:240],
            }
            for chunk, filename, _ in chunks
        ]

        try:
            resolved_chat_id = (chat_id or "").strip() or None
            owner_user_id = (user_id or "").strip().lower()
            resolved_title = None

            if resolved_chat_id:
                header = (
                    await session.execute(
                        select(ChatHeader).where(
                            ChatHeader.owner_user_id == owner_user_id,
                            ChatHeader.business_id == business_id,
                            ChatHeader.workspace_id == workspace_id,
                            ChatHeader.chat_id == resolved_chat_id,
                        )
                    )
                ).scalar_one_or_none()

                auto_title = build_chat_title(query)
                incoming_title = (chat_title or "").strip()
                if incoming_title and incoming_title.lower() not in {"new chat", "untitled chat"}:
                    title_candidate = incoming_title[:80]
                else:
                    title_candidate = auto_title

                if header is None:
                    header = ChatHeader(
                        owner_user_id=owner_user_id,
                        business_id=business_id,
                        workspace_id=workspace_id,
                        chat_id=resolved_chat_id,
                        title=title_candidate or "New chat",
                        deleted_at=None,
                    )
                    session.add(header)
                else:
                    if header.deleted_at is not None:
                        header.deleted_at = None
                    if not header.title or header.title.strip().lower() in {"new chat", "untitled chat"}:
                        header.title = title_candidate or header.title or "New chat"

                resolved_title = header.title

            chat_request = ChatRequest(
                business_id=business_id,
                workspace_id=workspace_id,
                user_id=owner_user_id or user_id,
                chat_header=resolved_chat_id,
                query_text=query,
                retrieved_chunk_ids=json.dumps([str(chunk.id) for chunk, _, _ in chunks]),
            )
            session.add(chat_request)
            await session.flush()
            chat_response = ChatResponse(
                request_id=chat_request.id,
                chat_header=resolved_chat_id,
                answer_text=answer,
                sources_json=json.dumps(sources),
                model_used=model,
                tokens_json=json.dumps(usage),
            )
            session.add(chat_response)
            await session.commit()
            log_chat(
                "CHAT_SAVED",
                "Chat request and response saved to DB",
                request_id=str(chat_request.id),
                chat_id=resolved_chat_id,
                chat_title=resolved_title,
            )
        except Exception as e:
            log_chat("CHAT_ERROR", f"Step failed: save to DB", step="save", error=str(e), error_type=type(e).__name__)
            raise

        return answer, sources, usage, resolved_chat_id, resolved_title

    def _mask_api_key(self, key: str | None) -> str:
        """Return masked key for logging (first 7 + ... + last 4). Never log full key."""
        if not key or not isinstance(key, str):
            return "(empty or not set)"
        key = key.strip()
        if len(key) <= 11:
            return "(too short to mask)"
        return f"{key[:7]}...{key[-4:]}"

    async def _call_openai(
        self,
        messages: list[dict],
        model: str,
        temperature: float,
        max_tokens: int,
        openai_api_key: str | None = None,
    ) -> dict:
        key = (openai_api_key or self.settings.openai_api_key) or ""
        key_set = bool(key and key.strip())
        log_chat(
            "CHAT_OPENAI_KEY_CHECK",
            "OpenAI API key from DB/env (masked)",
            key_set=key_set,
            key_length=len(key.strip()) if key else 0,
            masked_key=self._mask_api_key(key),
        )
        if not key_set:
            raise RuntimeError("OPENAI_API_KEY not configured. Set it in System configurations.")
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        request_body_log = json.dumps({"model": model, "message_count": len(messages), "temperature": temperature, "max_tokens": max_tokens, "message_content_lens": [len(m.get("content", "")) for m in messages]}, ensure_ascii=False)
        headers = {"Authorization": f"Bearer {key}"}
        try:
            async with httpx.AsyncClient(base_url=self.settings.openai_base_url, timeout=60) as client:
                log_chat("CHAT_OPENAI_SEND", "Sending request to OpenAI", model=model, base_url=self.settings.openai_base_url, request_body=request_body_log)
                response = await client.post("/chat/completions", json=payload, headers=headers)
                raw_response_text = response.text or ""
                status_code = response.status_code
                # Always log the raw API response first (success or error) so we never miss it
                log_chat(
                    "CHAT_OPENAI_API_RESPONSE",
                    "OpenAI API raw response (before raise_for_status)",
                    status_code=status_code,
                    response_body=raw_response_text,
                )
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as e:
                    log_chat("CHAT_ERROR", "OpenAI API returned error", step="openai_call", status_code=status_code, response_body=raw_response_text, error=str(e))
                    raise
                try:
                    response_json = response.json()
                except Exception as parse_err:
                    log_chat("CHAT_ERROR", "OpenAI response JSON parse failed", step="openai_call", response_body=raw_response_text, error=str(parse_err), error_type=type(parse_err).__name__)
                    raise
                log_chat("CHAT_OPENAI_RAW_RESPONSE", "OpenAI API raw response body (success)", raw_response=json.dumps(response_json, ensure_ascii=False))
                return response_json
        except httpx.HTTPStatusError:
            raise
        except Exception as e:
            log_chat("CHAT_ERROR", "OpenAI request failed (network/timeout/other)", step="openai_call", error=str(e), error_type=type(e).__name__)
            raise
