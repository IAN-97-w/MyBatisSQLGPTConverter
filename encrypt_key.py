from cryptography.fernet import Fernet
import json

KEY_FILE = "key.key"
CONFIG_FILE = "config.json"

def generate_key():
    key = Fernet.generate_key()
    with open(KEY_FILE, "wb") as key_file:
        key_file.write(key)
    return key

def encrypt_api_key(api_key, key):
    fernet = Fernet(key)
    return fernet.encrypt(api_key.encode()).decode()

if __name__ == "__main__":
    api_key = input("🔑 OpenAI GPT API 키 입력: ").strip()
    input_dir = input("📁 변환할 MyBatis XML 폴더 경로 (예: ./mybatis_oracle): ").strip()
    output_dir = input("📁 변환된 파일 저장 경로 (예: ./mybatis_postgresql): ").strip()

    key = generate_key()
    encrypted_key = encrypt_api_key(api_key, key)

    config = {
        "source_db": "oracle",
        "target_db": "postgresql",
        "input_dir": input_dir,
        "output_dir": output_dir,
        "encrypted_api_key": encrypted_key
    }

    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)

    print("✅ config.json 및 key.key 생성 완료")
