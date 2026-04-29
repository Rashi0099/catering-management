import os

ROOT_DIR = '/home/rasheed/Documents/catrin_boys_website/catering_project'
EXCLUDE_DIRS = {'venv', '.git', '__pycache__', 'media', 'static', '.gemini'}

def replace_in_files():
    for root, dirs, files in os.walk(ROOT_DIR):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for file in files:
            if file.endswith(('.html', '.py', '.txt', '.md')):
                path = os.path.join(root, file)
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    new_content = content.replace("Mastan <span>Catering & Services</span>", "Mastan <span>Catering & Services</span>")
                    new_content = new_content.replace("Mastan Catering & Services", "Mastan Catering & Services")
                    
                    if new_content != content:
                        with open(path, 'w', encoding='utf-8') as f:
                            f.write(new_content)
                        print(f"Updated {path}")
                except Exception as e:
                    print(f"Error reading {path}: {e}")

if __name__ == '__main__':
    replace_in_files()
