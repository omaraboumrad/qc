from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .api.routes import router
from .api.sse import sse_router

# Create FastAPI application
app = FastAPI(
    title="QC Network Traffic Shaping API",
    description="Backend API for network traffic shaping playground",
    version="0.1.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # Frontend dev server
        "http://frontend:3000",   # Frontend container
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(router, prefix="/api", tags=["api"])
app.include_router(sse_router, prefix="/api", tags=["sse"])


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "QC Network Traffic Shaping Backend",
        "version": "0.1.0",
        "endpoints": {
            "docs": "/docs",
            "health": "/api/health",
            "metrics": "/api/metrics/current",
            "stream": "/api/metrics/stream",
            "rules": "/api/rules"
        }
    }


@app.get("/health")
async def health():
    """Health check"""
    return {"status": "healthy"}
