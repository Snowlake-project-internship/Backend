from fastapi import APIRouter

from schemas.chat import ChatRequest, ChatResponse

router = APIRouter()


@router.post("/", response_model=ChatResponse)
def chat(req: ChatRequest):
    return ChatResponse(answer=f"Received: {req.message}")
