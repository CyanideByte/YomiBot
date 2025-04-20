from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn
import asyncio

from .query_processing import process_unified_query

app = FastAPI()

# CORS middleware to allow requests from the React frontend
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For development, allow all. Restrict in production.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    message: str

@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    # Pass only the user_query parameter, ignore the rest
    response = await process_unified_query(user_query=request.message)

    # Remove "Sources:" section and everything after it
    import re
    response = re.sub(r"\n*Sources:.*", "", response, flags=re.DOTALL)

    return JSONResponse(content={"response": response.strip()})

# Optional: for local testing
if __name__ == "__main__":
    uvicorn.run("src.osrs.llm.chat_endpoint:app", host="0.0.0.0", port=8000, reload=True)