from langchain.tools import tool
from typing import Optional
import logging
import os
from pathlib import Path
from datetime import datetime
import json

logger = logging.getLogger(__name__)


@tool
def file_operations_tool(
    action: str,
    content: Optional[str] = None,
    filename: Optional[str] = None,
    directory: Optional[str] = None,
    file_type: Optional[str] = "txt",
) -> str:
    """
    Save, read, list, or delete newsroom output files.

    Actions: save_file, read_file, list_files, delete_file, create_directory

    Args:
        action: The action to perform
        content: Content to write (save_file)
        filename: Filename — use TIMESTAMP for auto timestamp (e.g. "article_TIMESTAMP")
        directory: Directory path (defaults to ./output/articles)
        file_type: Extension — txt, md, json, html (default txt)

    Examples:
        file_operations_tool(action="save_file", content="...", filename="article_TIMESTAMP", file_type="md", directory="./output/articles")
        file_operations_tool(action="list_files", directory="./output/articles")
        file_operations_tool(action="read_file", filename="article_20260404_120000.md", directory="./output/articles")
    """
    try:
        if not directory:
            directory = "./output/articles"

        Path(directory).mkdir(parents=True, exist_ok=True)

        if action == "save_file":
            if not content:
                return "Error: content is required for save_file"
            if not filename:
                filename = f"file_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            if "TIMESTAMP" in filename:
                filename = filename.replace("TIMESTAMP", datetime.now().strftime("%Y%m%d_%H%M%S"))
            if not filename.endswith(f".{file_type}"):
                filename = f"{filename}.{file_type}"

            filepath = Path(directory) / filename
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            size = os.path.getsize(filepath)
            logger.info(f"[file_ops] Saved {filepath} ({size} bytes)")
            return f"Saved: {filepath} ({size} bytes)"

        elif action == "read_file":
            if not filename:
                return "Error: filename is required for read_file"
            filepath = Path(directory) / filename
            if not filepath.exists():
                return f"Error: File not found: {filepath}"
            with open(filepath, "r", encoding="utf-8") as f:
                return f.read()

        elif action == "list_files":
            path = Path(directory)
            if not path.exists():
                return f"Directory not found: {directory}"
            files = sorted(path.glob("*.*"))
            if not files:
                return f"No files in {directory}"
            lines = [f"Files in {directory}:"]
            for f in files:
                size = os.path.getsize(f)
                mtime = datetime.fromtimestamp(os.path.getmtime(f)).strftime("%Y-%m-%d %H:%M")
                lines.append(f"  {f.name}  ({size:,} bytes, {mtime})")
            return "\n".join(lines)

        elif action == "delete_file":
            if not filename:
                return "Error: filename is required for delete_file"
            filepath = Path(directory) / filename
            if not filepath.exists():
                return f"Error: File not found: {filepath}"
            os.remove(filepath)
            return f"Deleted: {filename}"

        elif action == "create_directory":
            Path(directory).mkdir(parents=True, exist_ok=True)
            return f"Created directory: {directory}"

        else:
            return f"Unknown action: {action}. Use: save_file, read_file, list_files, delete_file, create_directory"

    except Exception as e:
        logger.error(f"[file_ops] Error: {e}", exc_info=True)
        return f"Error: {str(e)}"
