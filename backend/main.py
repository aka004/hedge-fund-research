"""
FastAPI backend for Stock Screener.
"""

from app.api import dashboard, screener, stock
from app.models.schemas import HealthResponse
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Stock Screener API",
    description="Hedge Fund Research Stock Screener Backend",
    version="1.0.0",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite default port
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(screener.router)
app.include_router(stock.router)
app.include_router(dashboard.router)


@app.get("/")
async def root():
    return {"message": "Stock Screener API", "version": "1.0.0"}


@app.get("/health", response_model=HealthResponse)
async def health():
    return {"status": "healthy", "version": "1.0.0"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
