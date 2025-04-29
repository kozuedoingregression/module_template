from pydantic import BaseModel
from typing import Union, Dict, Any, List, Optional

class InputSchema(BaseModel):
    tool_name: str
    repo_url: str
    file_path: str
    tool_input_data: Optional[Union[Dict[str, Any], List[Dict[str, Any]], str]] = None
