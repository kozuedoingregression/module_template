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
    def __init__(self, tool_deployment: ToolDeployment, inputs: InputSchema, max_depth=3):
        self.tool_deployment = tool_deployment
        github_token = os.environ['GITHUB_TOKEN']
        if github_token is None:
            raise ValueError("Github token is not set")
        
        self.g = Github(github_token)
        self.repo_name = self.parse_repo_url(inputs.repo_url)
        self.repo = self.g.get_repo(self.repo_name)
        
        cache_type = 'repo_index'
        self.base_cache_dir = os.path.join('cache', self.repo_name)
        self.cache_dir = self.get_cache_dir(cache_type)
        self.max_depth = max_depth
        self.repo_index = defaultdict(list)
        self.stopwords = set(['the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'])
        
        self.load_cache()

    def get_file_content(self, inputs: InputSchema):
        try:
            file_content = self.repo.get_contents(inputs.file_path)
            if file_content.size > 1000000:  # 1MB limit
                return "File is too large to fetch content directly."
            content = base64.b64decode(file_content.content).decode('utf-8')
            return content
        except Exception as e:
            return f"Error fetching file: {str(e)}"

    def get_directory_structure(self, path="", prefix="", max_depth=2, current_depth=0, is_last=True):
        if current_depth > max_depth:
            return []
        try:
            contents = self.repo.get_contents(path)
        except Exception as e:
            return [f"{prefix}Error reading path {path}: {str(e)}"]

        contents = sorted(contents, key=lambda x: (x.type != 'dir', x.name.lower()))
        tree_lines = []

        for idx, content in enumerate(contents):
            is_last_item = idx == len(contents) - 1
            connector = "└── " if is_last_item else "├── "

            line = f"{prefix}{connector}{content.name}"
            if content.type == "dir":
                line += "/"
                tree_lines.append(line)
                extension = "    " if is_last_item else "│   "
                tree_lines.extend(self.get_directory_structure(
                    path=content.path,
                    prefix=prefix + extension,
                    max_depth=max_depth,
                    current_depth=current_depth + 1,
                    is_last=is_last_item
                ))
            else:
                tree_lines.append(line)
        return tree_lines
    
    def parse_repo_url(self, url):
        if "github.com/" not in url:
            raise ValueError("Invalid GitHub URL")
        path = url.split("github.com/", 1)[-1]
        return path.strip("/")
    
    def index_repo_file(self, inputs: InputSchema):
        file_path = inputs.file_path
        try:
            file_content = self.repo.get_contents(file_path)
            if file_content.size > 1000000:  # 1MB limit
                return "File is too large to fetch content directly."
            
            content = base64.b64decode(file_content.content).decode('utf-8')
            cleaned_content = self.clean_text(content)
            words = cleaned_content.split()

            for word in words:
                if file_path not in self.repo_index[word]:
                    self.repo_index[word].append(file_path)
                self.save_cache()
            return f"Indexing successful for file: {file_path}"
        except Exception as e:
            return f"Indexing failed for file: {file_path}. Error: {str(e)}"


    def search_repo(self, inputs: InputSchema, k=5):
        cleaned_query = self.clean_text(inputs.query)
        query_words = cleaned_query.split()
        file_scores = Counter()
        
        for word in query_words:
            for file_path in self.repo_index.get(word, []):
                file_scores[file_path] += 1
        
        if not file_scores:
            return "No matching files found for the given query."

        return file_scores.most_common(k)

    def clean_text(self, text):
        text = text.lower()
        text = text.translate(str.maketrans('', '', string.punctuation))
        text = re.sub(r'\d+', '', text)
        words = text.split()
        words = [word for word in words if word not in self.stopwords]
        return ' '.join(words)

    def clear_cache(self):
        self.repo_index.clear()
        cache_file = os.path.join(self.cache_dir, 'repo_index.pkl')
        if os.path.exists(cache_file):
            os.remove(cache_file)
        logging.info("Repository index cache cleared")
        return "Repository index cache cleared"

    def save_cache(self):
        with open(os.path.join(self.cache_dir, 'repo_index.pkl'), 'wb') as f:
            pickle.dump(dict(self.repo_index), f)
        logging.info("Repository index cache saved successfully.")

    def load_cache(self):
        repo_index_path = os.path.join(self.cache_dir, 'repo_index.pkl')
        if os.path.exists(repo_index_path):
            with open(repo_index_path, 'rb') as f:
                self.repo_index = defaultdict(list, pickle.load(f))
            logging.info("Repository index cache loaded successfully.")
            return True
        return False
    
    def get_cache_dir(self, cache_type):
        """Creates and returns a cache directory for a given type."""
        cache_dir = os.path.join(self.base_cache_dir, cache_type)
        os.makedirs(cache_dir, exist_ok=True)
        return cache_dir

def run(module_run: Dict):
    module_run = ToolRunInput(**module_run)
    module_run.inputs = InputSchema(**module_run.inputs)
    GitHubRepoTool = GitHubRepo(module_run,module_run.inputs)
    method = getattr(GitHubRepoTool, module_run.inputs.tool_name, None)
    if not method:
        raise ValueError(f"Method {module_run.inputs.tool_name} not found")
    if module_run.inputs.tool_name == "get_directory_structure":
        return method()
    elif module_run.inputs.tool_name == "clear_cache":
        return method()
    else:
        return method(module_run.inputs)
    
if __name__ == "__main__":
    import asyncio
    from naptha_sdk.client.naptha import Naptha # type: ignore 
    from naptha_sdk.configs import setup_module_deployment # type: ignore
    import os

    naptha = Naptha()

    deployment = asyncio.run(setup_module_deployment("tool", "github_integration_tool/configs/deployment.json", node_url = os.getenv("NODE_URL")))
    
    input_params_1 = {
        "tool_name": "get_file_content",
        "repo_url": "https://github.com/kozuedoingregression/attention-is-all-you-need",
        "file_path": "transformer/transformer_de_to_en.py"
    }

    input_params_2 = {
        "tool_name": "get_directory_structure",
        "repo_url": "https://github.com/kozuedoingregression/attention-is-all-you-need",
    }
    
    input_params_3 = {
        "tool_name": "index_repo_file",
        "repo_url": "https://github.com/kozuedoingregression/attention-is-all-you-need",
        "file_path": "transformer/transformer_de_to_en.py"
    }
    
    input_params_4 = {
        "tool_name": "search_repo",
        "repo_url": "https://github.com/kozuedoingregression/attention-is-all-you-need",
        "file_path": "transformer/transformer_de_to_en.py",
        "query": "decoder"
    }    
    
    input_params_5 = {
        "tool_name": "clear_cache",
        "repo_url": "https://github.com/kozuedoingregression/attention-is-all-you-need",
    }   
    
    module_run = {
        "inputs": input_params_5,
        "deployment": deployment,
        "consumer_id": naptha.user.id,
        # "signature": sign_consumer_id(naptha.user.id, os.getenv("PRIVATE_KEY_FULL_PATH"))
        "signature": ''
    }

    response = run(module_run)

    if module_run['inputs']['tool_name'] == 'get_directory_structure':
        print("Response:\n" + "\n".join(response))
    else:
        print("Response:", response)
