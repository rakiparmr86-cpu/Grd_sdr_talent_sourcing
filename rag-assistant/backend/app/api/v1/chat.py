from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.core.security import require_api_key
from app.models.schemas import ChatRequest, ChatResponse
from app.services.chat_service import ChatService

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    return await ChatService().chat(request)


@router.post("/stream")
async def stream_chat(request: ChatRequest) -> StreamingResponse:
    async def event_stream():
        async for token in ChatService().stream_chat(request):
            yield f"data: {token}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
