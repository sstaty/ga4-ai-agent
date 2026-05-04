from fastapi import FastAPI

app = FastAPI(title="GA4 AI Agent")


@app.get("/health")
def health():
    return {"status": "ok"}
