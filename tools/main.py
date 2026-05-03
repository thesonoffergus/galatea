"""Entry point for the Galatea developer tools web UI."""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("tools.app:app", host="127.0.0.1", port=8765, reload=True)
