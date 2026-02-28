import os
import sys
import subprocess
import shutil
import json
import pkg_resources
from groq import Groq

# =========================
# CONFIGURATION
# =========================

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.join(BASE_DIR, "workspace")
MEMORY_FILE  = os.path.join(BASE_DIR, "memory.json")

os.makedirs(PROJECT_ROOT, exist_ok=True)

# Set before starting: export GROQ_API_KEY=gsk_xxxx  (Windows: set GROQ_API_KEY=...)
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

# =========================
# LANGUAGE TEMPLATES
# =========================

LANGUAGE_TEMPLATES = {
    "python": ["main.py", "requirements.txt"],
    "node":   ["package.json", "index.js"],
    "cpp":    ["main.cpp", "CMakeLists.txt"],
    "java":   ["Main.java"]
}

# =========================
# MEMORY
# =========================

def load_memory():
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []
    return []

def save_memory(history):
    history = history[-4:]
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)

# =========================
# FILE UTILITIES
# =========================

def safe_workspace_path(path: str) -> str:
    """
    Always resolve paths inside PROJECT_ROOT/workspace.
    Blocks path traversal attacks (e.g. '../../etc/passwd').
    """
    path     = str(path).lstrip("/\\")
    full     = os.path.realpath(os.path.join(PROJECT_ROOT, path))
    root_abs = os.path.realpath(PROJECT_ROOT)
    if not full.startswith(root_abs + os.sep) and full != root_abs:
        raise ValueError(f"Path traversal blocked: {path}")
    return full

def find_file_by_name(filename):
    for root, dirs, files in os.walk(PROJECT_ROOT):
        if filename in files:
            return os.path.join(root, filename)
    return None

def find_folder_by_name(foldername):
    for root, dirs, files in os.walk(PROJECT_ROOT):
        if foldername in dirs:
            return os.path.join(root, foldername)
    return None

def read_file(path):
    try:
        full_path = safe_workspace_path(path)
    except ValueError as e:
        return str(e)
    if not os.path.exists(full_path):
        return f"File not found: {path}"
    with open(full_path, "r", encoding="utf-8") as f:
        return f.read()

def write_file(path, content):
    try:
        full_path = safe_workspace_path(path)
    except ValueError as e:
        return str(e)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"✅ File written: workspace/{path}"

def delete_file_smart(filename):
    path = find_file_by_name(filename)
    if path:
        os.remove(path)
        return f"🗑️ Deleted file: {path}"
    return f"File not found: {filename}"

def delete_folder(foldername):
    path = find_folder_by_name(foldername)
    if path:
        shutil.rmtree(path)
        return f"🗑️ Deleted folder: {path}"
    return f"Folder not found: {foldername}"

def create_directory(dirname):
    try:
        path = safe_workspace_path(dirname)
    except ValueError as e:
        return str(e)
    os.makedirs(path, exist_ok=True)
    return f"📁 Directory created: workspace/{dirname}"

def list_files():
    items = []
    for root, dirs, files in os.walk(PROJECT_ROOT):
        for d in sorted(dirs):
            rel = os.path.relpath(os.path.join(root, d), PROJECT_ROOT)
            items.append(f"[DIR]  {rel}")
        for f in sorted(files):
            rel = os.path.relpath(os.path.join(root, f), PROJECT_ROOT)
            items.append(f"[FILE] {rel}")
    return "\n".join(items) if items else "Workspace is empty."

def run_file(path):
    try:
        full_path = safe_workspace_path(path)
    except ValueError as e:
        return str(e)
    if not os.path.exists(full_path):
        return f"File not found: {path}"

    ext = os.path.splitext(full_path)[1].lower()

    if ext == ".py":
        # FIX: Use sys.executable instead of "python" — this guarantees we use
        # the exact Python interpreter running the server, avoiding [WinError 2]
        # on Windows where "python" may not be in PATH.
        cmd = [sys.executable, full_path]

    elif ext == ".js":
        node_exe = shutil.which("node") or shutil.which("node.exe")
        if not node_exe:
            return "❌ Node.js not found in PATH. Please install Node.js from https://nodejs.org"
        cmd = [node_exe, full_path]

    elif ext == ".cpp":
        gpp_exe = shutil.which("g++") or shutil.which("g++.exe")
        if not gpp_exe:
            return "❌ g++ not found in PATH. Please install MinGW-w64 or GCC."
        exe_path = full_path.replace(".cpp", "")
        if sys.platform == "win32":
            exe_path += ".exe"
        cr = subprocess.run([gpp_exe, full_path, "-o", exe_path],
                            capture_output=True, text=True)
        if cr.returncode != 0:
            return f"Compilation failed:\n{cr.stderr}"
        cmd = [exe_path]

    elif ext == ".java":
        javac_exe = shutil.which("javac") or shutil.which("javac.exe")
        if not javac_exe:
            return "❌ javac not found in PATH. Please install JDK."
        cr = subprocess.run([javac_exe, full_path],
                            capture_output=True, text=True)
        if cr.returncode != 0:
            return f"Compilation failed:\n{cr.stderr}"
        cls = os.path.splitext(os.path.basename(full_path))[0]
        java_exe = shutil.which("java") or shutil.which("java.exe")
        if not java_exe:
            return "❌ java not found in PATH."
        cmd = [java_exe, "-cp", os.path.dirname(full_path), cls]

    else:
        return f"Unsupported file type: {ext}"

    try:
        # FIX: Pass stdin=subprocess.DEVNULL so programs that call input() don't
        # hang forever waiting for keyboard input. They'll get an EOF instead and
        # raise EOFError, which is a clear signal vs. a silent freeze.
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30,
                                stdin=subprocess.DEVNULL,
                                cwd=os.path.dirname(full_path))
    except subprocess.TimeoutExpired:
        return "Execution timed out (30s)."
    except FileNotFoundError as e:
        return f"❌ Executable not found: {e}"

    return (f"▶ Output:\n{result.stdout}" if result.returncode == 0
            else f"✗ Error:\n{result.stderr or result.stdout}")

# =========================
# PROJECT BUILDER
# =========================

def create_project_structure(project_name, language):
    lang = language.strip().lower()
    if lang not in LANGUAGE_TEMPLATES:
        return (f"Unsupported language: {lang}. "
                f"Choose from: {list(LANGUAGE_TEMPLATES.keys())}")
    create_directory(project_name)
    for filename in LANGUAGE_TEMPLATES[lang]:
        write_file(f"{project_name}/{filename}", "")
    return f"📦 Project '{project_name}' created ({lang} template)."

# =========================
# DEPENDENCY MANAGEMENT
# =========================

def get_installed_packages():
    return {pkg.key: pkg.version for pkg in pkg_resources.working_set}

def install_dependency(package):
    # FIX: Use sys.executable -m pip instead of bare "pip" command.
    # On Windows, "pip" is often not in PATH but the module always works.
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", package],
        capture_output=True, text=True
    )
    return (f"✅ Installed: {package}"
            if result.returncode == 0
            else f"❌ Failed to install {package}:\n{result.stderr}")

def npm_install(project_folder: str) -> str:
    """Run npm install in a project folder inside workspace."""
    node_exe  = shutil.which("node") or shutil.which("node.exe")
    npm_exe   = shutil.which("npm")  or shutil.which("npm.cmd")
    if not node_exe or not npm_exe:
        return "❌ Node.js / npm not found in PATH. Install from https://nodejs.org"

    try:
        folder_path = safe_workspace_path(project_folder)
    except ValueError as e:
        return str(e)

    if not os.path.isdir(folder_path):
        return f"❌ Folder not found: {project_folder}"

    pkg_json = os.path.join(folder_path, "package.json")
    if not os.path.exists(pkg_json):
        return f"❌ No package.json found in {project_folder}"

    result = subprocess.run(
        [npm_exe, "install"],
        capture_output=True, text=True,
        cwd=folder_path, timeout=120
    )
    if result.returncode == 0:
        return f"✅ npm install completed in {project_folder}"
    return f"❌ npm install failed:\n{result.stderr or result.stdout}"


def manage_dependencies(project_name, dependency_text):
    installed = get_installed_packages()
    responses = []
    for dep in dependency_text.strip().splitlines():
        dep = dep.strip()
        if not dep:
            continue
        pkg_name = dep.split("==")[0].split(">=")[0].lower().strip()
        if pkg_name in installed:
            responses.append(f"✅ {pkg_name} already installed ({installed[pkg_name]})")
        else:
            responses.append(install_dependency(dep))
    return "\n".join(responses) if responses else "No packages specified."

# =========================
# SYSTEM PROMPT
# =========================

SYSTEM_PROMPT_TEMPLATE = """You are Medhavin, an autonomous AI coding agent running inside VS Code.
You MUST directly create/edit files using ACTION blocks. NEVER just explain or describe code.

Current workspace files:
{project_context}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STRICT OUTPUT RULES — VIOLATING THESE WILL BREAK THE SYSTEM
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. ALWAYS use ACTION blocks to create/edit/run files. NEVER use markdown code fences (``` ```) for file content.
2. Every ACTION block MUST end with END on its own line.
3. You CAN and SHOULD chain multiple ACTION blocks in one reply.
4. NEVER write code inside markdown — put ALL code inside CONTENT: ... END blocks.
5. After writing a requirements.txt, ALWAYS call manage_dependencies to install packages.
6. After writing a package.json with dependencies, ALWAYS call npm_install for that project folder.
7. When creating a full project, write ALL necessary files in one reply.

ACTION FORMAT:
ACTION: <action_name>
PATH: <relative/path>
CONTENT:
<content goes here>
END

Available actions:
  write_file          PATH: relative/file.py        CONTENT: file content
  read_file           PATH: relative/file.py        (no CONTENT needed)
  run_file            PATH: relative/file.py        (no CONTENT needed)
  delete_file         PATH: filename.py             (no CONTENT needed)
  delete_folder       PATH: foldername              (no CONTENT needed)
  create_directory    PATH: foldername              (no CONTENT needed)
  create_project      PATH: name|language           (e.g. myapp|python)
  manage_dependencies PATH: project_name            CONTENT: one pip package per line
  npm_install         PATH: project_folder          (runs npm install in that folder)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CORRECT EXAMPLES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Example 1 — Python file with dependency:
User: Create a Flask hello world app

ACTION: write_file
PATH: app.py
CONTENT:
from flask import Flask
app = Flask(__name__)

@app.route('/')
def hello():
    return 'Hello, World!'

if __name__ == '__main__':
    app.run(debug=True)
END

ACTION: manage_dependencies
PATH: .
CONTENT:
flask
END

Flask app created and dependency installed!

---

Example 2 — HTML file:
User: Create a hello world webpage

ACTION: write_file
PATH: index.html
CONTENT:
<!DOCTYPE html>
<html>
<head><title>Hello</title></head>
<body><h1>Hello, World!</h1></body>
</html>
END

Done! index.html created in your workspace.

---

Example 3 — Node.js project:
User: Create a Node.js express app

ACTION: write_file
PATH: myapp/package.json
CONTENT:
{{
  "name": "myapp",
  "version": "1.0.0",
  "main": "index.js",
  "dependencies": {{
    "express": "^4.18.0"
  }}
}}
END

ACTION: write_file
PATH: myapp/index.js
CONTENT:
const express = require('express');
const app = express();
app.get('/', (req, res) => res.send('Hello World!'));
app.listen(3000, () => console.log('Server running on port 3000'));
END

ACTION: npm_install
PATH: myapp
END

Node.js app created and dependencies installed!
"""

# =========================
# LLM
# =========================

def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token."""
    return len(text) // 4

def ask_llama(prompt: str, project_context: str, history: list) -> str:
    if not GROQ_API_KEY:
        raise EnvironmentError(
            "GROQ_API_KEY is not set.\n"
            "Before starting the server run:\n"
            "  Windows: set GROQ_API_KEY=your_groq_key_here\n"
            "  Linux/Mac: export GROQ_API_KEY=your_groq_key_here\n"
            "Get a free key at https://console.groq.com"
        )

    client = Groq(api_key=GROQ_API_KEY)

    # ── Smart context trimming to stay under ~4500 tokens ──────────────
    # 1. Truncate project_context if too large
    MAX_CONTEXT_CHARS = 800
    if len(project_context) > MAX_CONTEXT_CHARS:
        project_context = project_context[:MAX_CONTEXT_CHARS] + "\n...(truncated)"

    system_content = SYSTEM_PROMPT_TEMPLATE.format(project_context=project_context)

    # 2. Estimate total tokens, reduce history if needed
    base_tokens = _estimate_tokens(system_content) + _estimate_tokens(prompt)
    TOKEN_BUDGET = 4200  # safe limit under 6000 TPM
    available   = TOKEN_BUDGET - base_tokens

    trimmed_history = list(history)  # already [-4] from save_memory
    while trimmed_history and available < 800:
        trimmed_history = trimmed_history[2:]   # drop oldest pair
        history_tokens  = sum(_estimate_tokens(m["content"]) for m in trimmed_history)
        available       = TOKEN_BUDGET - base_tokens - history_tokens

    messages = [{"role": "system", "content": system_content}]
    messages.extend(trimmed_history)
    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        temperature=0.3,
        max_tokens=3000,
    )
    return response.choices[0].message.content

# =========================
# ACTION PARSER
# =========================

def parse_actions(response: str):
    """
    Parses the LLM response for ACTION blocks.
    Handles:
    - Multiple chained actions
    - Missing END marker (flushes last action anyway)
    - Markdown code fence stripping
    """
    # Strip all ``` fences (including ```python, ```js, etc.)
    clean = []
    for line in response.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            continue
        clean.append(line)
    lines = clean

    actions       = []
    action        = None
    path          = None
    content_lines = []
    content_mode  = False

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("ACTION:"):
            # Flush previous action if any (handles missing END)
            if action is not None:
                actions.append((action, path, "\n".join(content_lines)))
                content_lines = []
            action       = stripped[len("ACTION:"):].strip()
            path         = None
            content_mode = False

        # Only parse PATH if we are NOT inside content_mode
        # (prevents PATH: lines inside file content from being misinterpreted)
        elif stripped.startswith("PATH:") and action is not None and not content_mode:
            path = stripped[len("PATH:"):].strip()

        elif stripped == "CONTENT:" and action is not None:
            content_mode = True

        elif stripped == "END":
            if action is not None:
                actions.append((action, path, "\n".join(content_lines)))
            action        = None
            path          = None
            content_lines = []
            content_mode  = False

        elif content_mode:
            content_lines.append(line)

    # Flush any trailing action without END
    if action is not None:
        actions.append((action, path, "\n".join(content_lines)))

    return actions

# =========================
# MAIN ENTRY POINT
# =========================

def run_medhavin(prompt: str) -> dict:
    history         = load_memory()
    project_context = list_files()

    raw_output = ask_llama(prompt, project_context, history)

    history.append({"role": "user",      "content": prompt})
    history.append({"role": "assistant", "content": raw_output})
    save_memory(history)

    actions = parse_actions(raw_output)

    if not actions:
        # Plain conversational reply — no file ops
        return {"status": "response", "message": raw_output}

    results = []

    for action, path, content in actions:
        action = action.lower().strip()

        if action == "write_file":
            result_msg = write_file(path, content)
            results.append(result_msg)

            # ── Auto-install Python deps when requirements.txt is written ──
            if path and os.path.basename(path).lower() == "requirements.txt" and content.strip():
                results.append("🔧 Auto-installing Python dependencies from requirements.txt...")
                project_dir = os.path.dirname(path) or "."
                results.append(manage_dependencies(project_dir, content))

            # ── Auto-run npm install when package.json is written with deps ──
            if path and os.path.basename(path).lower() == "package.json":
                try:
                    pkg_data = json.loads(content)
                    has_deps = pkg_data.get("dependencies") or pkg_data.get("devDependencies")
                    if has_deps:
                        project_dir = os.path.dirname(path) or "."
                        results.append("🔧 Auto-running npm install for package.json...")
                        results.append(npm_install(project_dir))
                except (json.JSONDecodeError, Exception):
                    pass  # If JSON parse fails, skip npm install silently

        elif action == "read_file":
            results.append(read_file(path))

        elif action == "run_file":
            results.append(run_file(path))

        elif action == "delete_file":
            results.append(delete_file_smart(path))

        elif action == "delete_folder":
            results.append(delete_folder(path))

        elif action == "create_directory":
            results.append(create_directory(path))

        elif action == "create_project":
            if not path or "|" not in path:
                results.append(
                    "create_project requires PATH in format: project_name|language\n"
                    f"Example: my_app|python"
                )
            else:
                project_name, language = path.split("|", 1)
                results.append(
                    create_project_structure(project_name.strip(), language.strip())
                )

        elif action == "manage_dependencies":
            results.append(manage_dependencies(path or "", content))

        elif action == "npm_install":
            results.append(npm_install(path or "."))

        else:
            results.append(f"⚠️ Unknown action: '{action}'")

    final_output = "\n\n".join(results)

    # Append the LLM's descriptive text (non-action content) after results
    non_action_text = _extract_non_action_text(raw_output)
    if non_action_text.strip():
        final_output = final_output + "\n\n" + non_action_text.strip()

    return {"status": "completed", "output": final_output}


def _extract_non_action_text(raw_output: str) -> str:
    """
    Extracts lines from the LLM response that are NOT part of ACTION blocks.
    This gives users the natural language explanation alongside the action results.
    """
    lines         = raw_output.splitlines()
    in_block      = False
    outside_lines = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("ACTION:"):
            in_block = True
        elif stripped == "END":
            in_block = False
        elif not in_block:
            if not stripped.startswith("```"):
                outside_lines.append(line)

    return "\n".join(outside_lines)
