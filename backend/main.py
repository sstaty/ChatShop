from fastapi import FastAPI

app = FastAPI(title="ChatShop API", version="0.1.0")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
