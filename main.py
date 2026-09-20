import os
from dotenv import load_dotenv
import uvicorn

load_dotenv()

if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    
    print(f"Starting YUVI Server on http://{host}:{port}")
    uvicorn.run(
        "server:app",
        host=host,
        port=port,
        reload=False
    )

