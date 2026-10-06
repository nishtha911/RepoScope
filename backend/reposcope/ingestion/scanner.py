from hashlib import sha256
from pathlib import Path

#why are we hashing?
#to track edited files, bascailly for each file in repo we make a hash it using sha256
#in new commit we check if hash is same: if yes then file unchanged if no:file has been changed
#better than manually comparing files line by line

LANGUAGE_BY_EXTENSION = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cs": "csharp",
    ".rb": "ruby",
    ".php": "php",
    ".sql": "sql",
}


def detect_extension(file_path: str | Path) -> str: #accepts a string or path object returns a string
    return Path(file_path).suffix.lower() #.suffix extracts the file extention along with the dot ex: .txt,.py


def detect_language(file_path: str | Path) -> str:
    extension = detect_extension(file_path)
    return LANGUAGE_BY_EXTENSION.get(extension, "unknown") #check against our list of languages


def hash_content(content: bytes) -> str:#pythons sha hasher takes bytes as input
    hash_object = sha256(content)
    hash_string = hash_object.hexdigest() #.hexdigest matlab return as a hexadecimal string instead of raw bytes form
    return hash_string