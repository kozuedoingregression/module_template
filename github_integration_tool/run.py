#!/usr/bin/env python
import os
import base64
import logging
import asyncio
import pickle
import string
import re
from collections import defaultdict, Counter
from github import Github # type: ignore
from dotenv import load_dotenv # type: ignore
from typing import Dict
from naptha_sdk.schemas import ToolDeployment, ToolRunInput # type: ignore
from naptha_sdk.user import sign_consumer_id # type: ignore 
from naptha_sdk.utils import get_logger # type: ignore 
from github_integration_tool.schemas import InputSchema # type: ignore

load_dotenv()

logger = get_logger(__name__)

# Global variable for repository processing status
repo_processing_event = asyncio.Event()

class GitHubRepo:
    def __init__(self, tool_deployment: ToolDeployment, inputs: InputSchema):
        self.tool_deployment = tool_deployment
        github_token = os.environ['GITHUB_TOKEN']
        if github_token is None:
            raise ValueError("Github token is not set")
        
        self.g = Github(github_token)
        self.repo_name = self.parse_repo_url(inputs.repo_url)
        self.repo = self.g.get_repo(self.repo_name)

    def get_file_content(self, inputs: InputSchema):
        try:
            file_content = self.repo.get_contents(inputs.file_path)
            print(f"file connn: {file_content}")
            if file_content.size > 1000000:  # 1MB limit
                return "File is too large to fetch content directly."
            content = base64.b64decode(file_content.content).decode('utf-8')
            return content
        except Exception as e:
            return f"Error fetching file: {str(e)}"

    def get_directory_structure(self, path="", prefix="", max_depth=2, current_depth=0):
        if current_depth > max_depth:
            return []

        contents = self.repo.get_contents(path)
        structure = []
        for content in contents:
            if content.type == "dir":
                structure.append(f"{prefix}{content.name}/")
                if current_depth < max_depth:
                    structure.extend(self.get_directory_structure(
                        content.path, 
                        prefix + "  ", 
                        max_depth, 
                        current_depth + 1
                    ))
            else:
                structure.append(f"{prefix}{content.name}")
        return structure
    
    def parse_repo_url(self, url):
        if "github.com/" not in url:
            raise ValueError("Invalid GitHub URL")
        path = url.split("github.com/", 1)[-1]
        return path.strip("/")
    
def run(module_run: Dict):
    module_run = ToolRunInput(**module_run)
    module_run.inputs = InputSchema(**module_run.inputs)
    basic_module = GitHubRepo(module_run,module_run.inputs)
    method = getattr(basic_module, module_run.inputs.tool_name, None)
    if not method:
        raise ValueError(f"Method {module_run.inputs.tool_name} not found")
    return method(module_run.inputs)

if __name__ == "__main__":
    import asyncio
    from naptha_sdk.client.naptha import Naptha # type: ignore 
    from naptha_sdk.configs import setup_module_deployment # type: ignore
    import os

    naptha = Naptha()

    deployment = asyncio.run(setup_module_deployment("tool", "github_integration_tool/configs/deployment.json", node_url = os.getenv("NODE_URL")))
    
    input_params = {
        "tool_name": "get_file_content",
        "repo_url": "https://github.com/kozuedoingregression/attention-is-all-you-need",
        "file_path": "test.py"
    }

    module_run = {
        "inputs": input_params,
        "deployment": deployment,
        "consumer_id": naptha.user.id,
        # "signature": sign_consumer_id(naptha.user.id, os.getenv("PRIVATE_KEY_FULL_PATH"))
        "signature": ''
    }

    response = run(module_run)

    print("Response: ", response)