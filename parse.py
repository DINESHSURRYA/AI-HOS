import os
import re

with open('code.txt', 'r', encoding='utf-8') as f:
    lines = f.read().split('\n')

headers = []
for i in range(len(lines) - 2):
    if lines[i+2].strip() == 'Copy':
        lang = lines[i+1].strip().lower()
        if lang in ['txt', 'python', 'dockerfile', 'yaml', 'yml', 'json', 'tsx', 'ts', 'typescript', 'bash', 'sh', 'javascript', 'js', 'plain']:
            filepath_line = lines[i].strip()
            filepath = filepath_line.split(' - ')[0].strip()
            if '/' in filepath or '.' in filepath or 'Dockerfile' in filepath or 'ai-hos' in filepath:
                headers.append((i, filepath, lang))

for idx, (i, filepath, lang) in enumerate(headers):
    print(f"Found file: {filepath} at line {i} with lang {lang}")

