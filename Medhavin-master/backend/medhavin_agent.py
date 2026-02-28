from groq import Groq
import os
import subprocess
import shutil
import json
import pkg_resources
import subprocess

# =========================
# LANGUAGE TEMPLATES
# =========================

LANGUAGE_TEMPLATES = {
    "python": ["main.py", "requirements.txt"],
    "node": ["package.json", "index.js"],
    "cpp": ["main.cpp", "CMakeLists.txt"],
    "java": ["Main.java"]
}
# =========================
# DEPENDENCY MANAGEMENT
# =========================

def get_installed_packages():
    installed = {}
    for pkg in pkg_resources.working_set:
        installed[pkg.key] = pkg.version
    return installed


def install_dependency(package):
    result = subprocess.run(
        ["pip", "install", package],
        capture_output=True,
        text=True
    )
    if result.returncode == 0:
        return f"Installed: {package}"
    else:
        return f"Failed to install {package}:\n{result.stderr}"


def manage_dependencies(project_name, dependency_text):
    installed = get_installed_packages()
    responses = []

    deps = dependency_text.strip().split("\n")

    for dep in deps:
        dep = dep.strip()
        if not dep:
            continue

        pkg_name = dep.split("==")[0].split(">=")[0].lower()

        if pkg_name in installed:
            responses.append(f"{pkg_name} already installed ({installed[pkg_name]})")
        else:
            responses.append(install_dependency(dep))

    return "\n".join(responses)
# =========================
# PROJECT ROOT
# =========================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.join(BASE_DIR, "workspace")
MEMORY_FILE = os.path.join(BASE_DIR, "memory.json")

os.makedirs(PROJECT_ROOT, exist_ok=True)

# =========================
# MEMORY
# =========================

def load_memory():
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_memory(history):
    history = history[-20:]  # keep last 20 exchanges
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)

# =========================
# FILE UTILITIES
# =========================
def safe_path(path: str):
    path = path.lstrip("/\\")  # remove absolute slash
    return os.path.join(BASE_DIR, path)

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
    full_path = os.path.join(PROJECT_ROOT, path)
    if not os.path.exists(full_path):
        return "File does not exist."
    with open(full_path, "r", encoding="utf-8") as f:
        return f.read()

def write_file(path, content):
    full_path = safe_path(path)

    os.makedirs(os.path.dirname(full_path), exist_ok=True)

    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)

    return f"File created at {full_path}"

def delete_file_smart(filename):
    path = find_file_by_name(filename)
    if path:
        os.remove(path)
        return f"Deleted file: {path}"
    return "File not found."

def delete_folder(foldername):
    path = find_folder_by_name(foldername)
    if path:
        shutil.rmtree(path)
        return f"Deleted folder: {path}"
    return "Folder not found."

def create_directory(dirname):
    path = os.path.join(PROJECT_ROOT, dirname)
    os.makedirs(path, exist_ok=True)
    return f"Directory created: {path}"

def list_files():
    items = []
    for root, dirs, files in os.walk(PROJECT_ROOT):
        for d in dirs:
            relative = os.path.relpath(os.path.join(root, d), PROJECT_ROOT)
            items.append(f"[DIR] {relative}")
        for f in files:
            relative = os.path.relpath(os.path.join(root, f), PROJECT_ROOT)
            items.append(f"[FILE] {relative}")
    return "\n".join(items) if items else "Workspace empty."

def run_file(path):
    full_path = os.path.join(PROJECT_ROOT, path)

    if not os.path.exists(full_path):
        return "File does not exist."

    ext = os.path.splitext(full_path)[1]

    if ext == ".py":
        cmd = ["python", full_path]

    elif ext == ".js":
        cmd = ["node", full_path]

    elif ext == ".cpp":
        exe_path = full_path.replace(".cpp", ".exe")
        compile_cmd = ["g++", full_path, "-o", exe_path]
        compile = subprocess.run(compile_cmd, capture_output=True, text=True)
        if compile.returncode != 0:
            return f"Compilation failed:\n{compile.stderr}"
        cmd = [exe_path]

    elif ext == ".java":
        compile = subprocess.run(["javac", full_path], capture_output=True, text=True)
        if compile.returncode != 0:
            return f"Compilation failed:\n{compile.stderr}"
        class_name = os.path.splitext(os.path.basename(full_path))[0]
        cmd = ["java", "-cp", os.path.dirname(full_path), class_name]

    else:
        return "Unsupported file type."

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0:
        return f"Execution successful:\n{result.stdout}"
    else:
        return f"Execution failed:\n{result.stderr}"

# =========================
# PROJECT BUILDER
# =========================

def create_project_structure(project_name, language):
    if language not in LANGUAGE_TEMPLATES:
        return f"Unsupported language: {language}"

    create_directory(project_name)

    for filename in LANGUAGE_TEMPLATES[language]:
        write_file(f"{project_name}/{filename}", "")

    return f"Project '{project_name}' created with {language} template."

# =========================
# LLM INTERACTION
# =========================

def ask_llama(prompt, project_context, history):

    client = Groq(api_key="groq api key")

    system_prompt = f"""
You are Medhavin, an autonomous coding agent.

Project files:
{project_context}

Follow action format strictly when needed.
"""

    messages = [
        {"role": "system", "content": system_prompt}
    ]

    # Add history
    for item in history:
        messages.append(item)

    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=messages,
        temperature=0.3
    )

    return response.choices[0].message.content

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": prompt})

    response = ollama.chat(
        model="",
        messages=messages
    )

    return response["message"]["content"]

# =========================
# ACTION PARSER
# =========================

def parse_actions(response):

    response = response.replace("```", "")
    lines = response.splitlines()

    actions = []
    action = None
    path = None
    content_lines = []
    content_mode = False

    for line in lines:

        if line.startswith("ACTION:"):
            if action:
                actions.append((action, path, "\n".join(content_lines)))
                content_lines = []
            action = line.replace("ACTION:", "").strip()
            path = None
            content_mode = False

        elif line.startswith("PATH:"):
            path = line.replace("PATH:", "").strip()

        elif line.strip() == "CONTENT:":
            content_mode = True

        elif line.strip() == "END":
            if action:
                actions.append((action, path, "\n".join(content_lines)))
            action = None
            path = None
            content_lines = []
            content_mode = False

        elif content_mode:
            content_lines.append(line)

    return actions

# =========================
# MAIN EXECUTION
# =========================

def run_medhavin(prompt: str):

    history = load_memory()
    project_context = list_files()

    raw_output = ask_llama(prompt, project_context, history)

    history.append({"role": "user", "content": prompt})
    history.append({"role": "assistant", "content": raw_output})
    save_memory(history)

    actions = parse_actions(raw_output)

    if not actions:
        return {
            "status": "response",
            "message": raw_output
        }

    final_output = ""
 
    for action, path, content in actions:

        if action == "write_file":
            final_output = write_file(path, content)

        elif action == "read_file":
            final_output = read_file(path)

        elif action == "run_file":
            final_output = run_file(path)

        elif action == "delete_file":
            final_output = delete_file_smart(path)

        elif action == "delete_folder":
            print("RAW LLM OUTPUT:")
            print(raw_output)
            final_output = delete_folder(path)

        elif action == "create_directory":
            final_output = create_directory(path)
        elif action == "create_project":
    # path format: project_name|language
             project_name, language = path.split("|")
             final_output = create_project_structure(project_name.strip(), language.strip())
        elif action == "manage_dependencies":
             final_output = manage_dependencies(path, content)

    return {
        "status": "completed",
        "output": final_output
    }