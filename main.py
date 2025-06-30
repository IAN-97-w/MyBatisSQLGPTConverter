import os
import json
import difflib
from bs4 import BeautifulSoup, CData
from cryptography.fernet import Fernet
from openai import OpenAI
from html import unescape

CONFIG_FILE = "config.json"
KEY_FILE = "key.key"

# 🔐 암호화 관련
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

# 📄 설정 로드
def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

# 📁 XML 파일 찾기
def find_xml_files(base_dir):
    for root, _, files in os.walk(base_dir):
        for file in files:
            if file.endswith(".xml"):
                yield os.path.join(root, file)

# 🔁 GPT로 쿨리 변환
def convert_sql_with_gpt(sql, source_db, target_db, client):
    prompt = f"""You are an expert in SQL migration. Convert the following SQL from {source_db.upper()} to {target_db.upper()}.

This SQL is used inside a MyBatis XML file. Only return the converted SQL query itself, without any explanation, markdown formatting, or comments.

- Do not wrap with ```sql
- Do not add any comments or descriptions
- Do not change MyBatis variables like #{{param}} or ${{param}}
- Preserve indentation as much as possible

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

# 🔎 diff 생성
def generate_diff(original, converted):
    return '\n'.join(difflib.unified_diff(
        original.strip().splitlines(),
        converted.strip().splitlines(),
        fromfile='original_sql',
        tofile='converted_sql',
        lineterm=''
    ))

# 🔄 CDATA 처리

def extract_inner_text_preserve_cdata(tag):
    contents = tag.contents
    if contents and isinstance(contents[0], CData):
        return str(contents[0]), True
    return tag.text.strip(), False

def replace_inner_text_preserve_cdata(tag, new_text, was_cdata):
    tag.clear()
    clean_text = unescape(new_text.strip())
    if was_cdata or '<' in clean_text or '>' in clean_text:
        tag.append(CData("\n" + clean_text + "\n"))
    else:
        tag.append("\n" + clean_text + "\n")

# 🤠 XML 파일 단위 처리
def process_xml_file(filepath, input_dir, output_dir, diff_dir, error_log, source_db, target_db, client):
    with open(filepath, "r", encoding="utf-8") as file:
        soup = BeautifulSoup(file, "xml")

    changed = False
    for tag_name in ["insert", "update", "delete", "select"]:
        for stmt in soup.find_all(tag_name):
            original_sql, is_cdata = extract_inner_text_preserve_cdata(stmt)
            converted_sql = convert_sql_with_gpt(original_sql, source_db, target_db, client)
            converted_sql = unescape(converted_sql)

            if converted_sql != original_sql:
                replace_inner_text_preserve_cdata(stmt, converted_sql, is_cdata)
                changed = True

                relative_path = os.path.relpath(filepath, start=input_dir)
                diff_path = os.path.join(diff_dir, relative_path + ".diff")
                os.makedirs(os.path.dirname(diff_path), exist_ok=True)
                with open(diff_path, "w", encoding="utf-8") as diff_file:
                    diff_file.write(generate_diff(original_sql, converted_sql))

    relative_path = os.path.relpath(filepath, start=input_dir)
    output_path = os.path.join(output_dir, relative_path)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as out_file:
        out_file.write(str(soup))

    print(f"{'✅' if changed else '➖'} {filepath} → {output_path}")

# 📂 전체 디렉터리 처리
def convert_directory(input_dir, output_dir, source_db, target_db, client):
    diff_dir = os.path.join(output_dir, "__diffs__")
    error_log = []
    for xml_file in find_xml_files(input_dir):
        process_xml_file(xml_file, input_dir, output_dir, diff_dir, error_log, source_db, target_db, client)

    if error_log:
        with open(os.path.join(output_dir, "conversion_errors.log"), "w", encoding="utf-8") as log_file:
            for path, err in error_log:
                log_file.write(f"{path}: {err}\n")
        print(f"⚠️ 변환 실패 {len(error_log)}간 → conversion_errors.log 확인 요망")

# ▶ 실행
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
