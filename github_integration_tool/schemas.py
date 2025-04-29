from pydantic import BaseModel
from typing import Optional

class InputSchema(BaseModel):
    tool_name: str
    repo_url: str
    file_path: Optional[str] = None
    query: Optional[str] = None
