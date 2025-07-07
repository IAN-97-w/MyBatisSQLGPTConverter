import os
import json
import difflib
import re
from bs4 import BeautifulSoup
from cryptography.fernet import Fernet
from openai import OpenAI
from html import unescape

CONFIG_FILE = "config.json"
KEY_FILE = "key.key"

def generate_key():
    if not os.path.exists(KEY_FILE):
        key = Fernet.generate_key()
        with open(KEY_FILE, "wb") as key_file:
            key_file.write(key)

def load_key():
    with open(KEY_FILE, "rb") as key_file:
        return key_file.read()

def decrypt_api_key(encrypted_key):
    key = load_key()
    return Fernet(key).decrypt(encrypted_key.encode()).decode()

def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def find_xml_files(base_dir):
    for root, _, files in os.walk(base_dir):
        for file in files:
            if file.endswith(".xml"):
                yield os.path.join(root, file)

def convert_sql_with_gpt(sql, source_db, target_db, client):
    prompt = f"""You are an expert in SQL migration. Convert the following SQL from {source_db.upper()} to {target_db.upper()}.

This SQL is used inside a MyBatis XML file. Only return the converted SQL query itself, without any explanation, markdown formatting, or comments.
- Only return the converted SQL statement itself, and nothing else.
- The output must be strictly the converted query only — no wrapping code, no explanations, no PL/pgSQL, no syntax wrappers.
- Do not use any Markdown code block syntax such as triple backticks (```), ```sql, or ```xml.
- Do not add any comments or descriptions
- Do not change MyBatis variables like #{{param}} or ${{param}}
- Preserve indentation as much as possible
- Preserve all MyBatis dynamic SQL tags such as <if>, <choose>, <when>, <otherwise>, <include>, <where>, <set>, <trim>, etc.
- Do not modify or remove any MyBatis XML tags or expressions
- Do not wrap the whole SQL in CDATA unless absolutely necessary. Preserve original structure.
- Do not wrap the entire SQL block in CDATA. Only wrap XML-sensitive characters such as <, >, or & with CDATA, and only if necessary — preserve CDATA at its original positions.
- Do not escape XML characters like < or >. Always output them as raw characters, not as &lt; or &gt;.
- Prefix all table names in the converted SQL with "TABLESPACE." (e.g., "SELECT * FROM USERS" → "SELECT * FROM TABLESPACE.USERS")
- If the original SQL contains any CDATA sections (e.g., <![CDATA[>]]>), you must preserve them exactly as they are — same content, same position. Do not move, wrap, remove, or alter any CDATA blocks.
- Do not wrap the entire SQL in a CDATA block. Only preserve or insert CDATA around specific characters if it was already present in the input.

SQL:
{sql}
"""
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": f"You are an expert in SQL migration from {source_db.upper()} to {target_db.upper()}."
                },
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"-- 변환 실패: {str(e)}\n{sql}"

def generate_diff(original, converted):
    return '\n'.join(difflib.unified_diff(
        original.strip().splitlines(),
        converted.strip().splitlines(),
        fromfile='original_sql',
        tofile='converted_sql',
        lineterm=''
    ))

def clean_gpt_output(sql: str) -> str:
    lines = sql.strip().splitlines()
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            continue
        if stripped.lower().startswith(("do $$", "begin", "declare", "exception")):
            continue
        if stripped.lower() in {"end;", "end"}:
            continue
        if re.search(r'```(sql|xml)?', stripped, re.IGNORECASE):
            continue
        cleaned.append(line)
    return "\n".join(cleaned).strip()

def extract_inner_text_preserve_cdata_from_text(xml_text: str, tag: str, tag_obj) -> tuple[str, bool]:
    """
    원본 xml_text에서 <tag>...</tag> 블록을 정규식으로 추출해, 내부 SQL을 그대로 반환 (CDATA 포함)
    """
    tag_name = tag.lower()

    # <select ...> ... </select> 내부 추출
    pattern = re.compile(
        rf"<{tag_name}[^>]*>(.*?)</{tag_name}>",
        re.DOTALL | re.IGNORECASE
    )

    matches = list(pattern.finditer(xml_text))
    if not matches:
        return tag_obj.decode_contents().strip(), False

    # 첫 번째 매치라도 무조건 채택
    body = matches[0].group(1).strip()
    is_cdata = "<![CDATA[" in body
    return body, is_cdata


def process_xml_file(filepath, input_dir, output_dir, diff_dir, error_log, source_db, target_db, client):
    with open(filepath, "r", encoding="utf-8") as f:
        original_text = f.read()

        pattern = re.compile(r"<(select|insert|update|delete)([^>]*)>([\s\S]*?)</\1>", re.IGNORECASE)
        changed = False

        def gpt_replacer(match):
            nonlocal changed
            tag, attrs, inner = match.groups()
            original_sql = inner.strip()
            print(">>> original_sql")
            print(original_sql)
            converted_sql = convert_sql_with_gpt(original_sql, source_db, target_db, client)
            print(">>> converted_sql")
            print(converted_sql)
            converted_sql = unescape(converted_sql)

            if converted_sql != original_sql:
                changed = True
                diff_path = os.path.join(diff_dir, os.path.relpath(filepath, input_dir)) + ".diff"
                os.makedirs(os.path.dirname(diff_path), exist_ok=True)
                with open(diff_path, "w", encoding="utf-8") as d:
                    d.write(generate_diff(original_sql, converted_sql))
                return f"<{tag}{attrs}>\n{converted_sql}\n</{tag}>"
            else:
                return match.group(0)

        new_text = pattern.sub(gpt_replacer, original_text)

        output_path = os.path.join(output_dir, os.path.relpath(filepath, input_dir))
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(new_text)

        print(f"{'✅' if changed else '➖'} {filepath} → {output_path}")

def convert_directory(input_dir, output_dir, source_db, target_db, client):
    diff_dir = os.path.join(output_dir, "__diffs__")
    error_log = []
    for xml_file in find_xml_files(input_dir):
        process_xml_file(xml_file, input_dir, output_dir, diff_dir, error_log, source_db, target_db, client)

    if error_log:
        with open(os.path.join(output_dir, "conversion_errors.log"), "w", encoding="utf-8") as log_file:
            for path, err in error_log:
                log_file.write(f"{path}: {err}\n")
        print(f"⚠️ 변환 실패 {len(error_log)}건 → conversion_errors.log 확인 요망")

if __name__ == "__main__":
    if not os.path.exists(CONFIG_FILE):
        print("❌ config.json 파일이 없습니다.")
        exit(1)

    generate_key()
    config = load_config()

    try:
        decrypted_api_key = decrypt_api_key(config["encrypted_api_key"])
        client = OpenAI(api_key=decrypted_api_key)
    except Exception as e:
        print(f"❌ API 키 복호화 실패: {e}")
        exit(1)

    convert_directory(
        input_dir=config["input_dir"],
        output_dir=config["output_dir"],
        source_db=config["source_db"],
        target_db=config["target_db"],
        client=client
    )
