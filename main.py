from fastapi import FastAPI

from app import create_app


def get_application() -> FastAPI:
    return create_app()


app = get_application()


@app.get("/healthz", tags=["health"]) 
def health_check():
    return {"status": "ok"}




if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

