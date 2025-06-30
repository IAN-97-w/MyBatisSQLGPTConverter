
# MyBatisSQLGPTConverter

AI 기반의 SQL 마이그레이션 도구입니다.  
Oracle, PostgreSQL, MariaDB 등 다양한 RDBMS 간 SQL을 변환하며, MyBatis XML 파일 내 SQL을 자동으로 읽고 변환 결과를 반영합니다.

---

## 🔧 기능 소개

- 💡 Oracle → PostgreSQL, MariaDB 등 다양한 DB 간 SQL 자동 변환
- 📄 MyBatis XML 파일 내 `<select>`, `<insert>`, `<update>`, `<delete>` 태그 처리
- 🤖 GPT-4o를 사용한 자연어 기반 SQL 변환
- 🔐 OpenAI API 키 암호화 및 안전한 저장
- 📂 디렉토리 단위 일괄 변환 및 diff 로그 생성
- 🧠 CDATA 유지 및 부등호(&lt;, &gt;) 자동 복원

---

## 🗂 디렉토리 구조

```
project/
├── input/                # 원본 MyBatis XML 파일
├── output/               # 변환된 결과 XML 파일
├── __diffs__/            # SQL 변환 전후 diff 파일
├── config.json           # 설정 파일
├── key.key               # 암호화 키 파일 (자동 생성)
├── main.py               # 메인 실행 파일
└── README.md             # 설명서
```

---

## ⚙️ 사용법

### 1. 사전 준비

1. `pip install -r requirements.txt`  
2. `config.json` 생성:

```json
{
  "input_dir": "input",
  "output_dir": "output",
  "source_db": "oracle",
  "target_db": "postgresql",
  "encrypted_api_key": "암호화된API키문자열"
}
```

> API 키는 `key.key`를 기반으로 암호화된 문자열을 `encrypted_api_key`에 넣어야 합니다.

### 2. API 키 암호화

```bash
python encrypt_key.py
```

### 3. 실행

```bash
python main.py
```

---

## ✅ 변환 예시

**변환 전 (Oracle):**
```xml
<select id="selectSample">
  SELECT TO_CHAR(SYSDATE, 'YYYYMMDD') FROM DUAL
</select>
```

**변환 후 (PostgreSQL):**
```xml
<select id="selectSample">
  SELECT TO_CHAR(NOW(), 'YYYYMMDD')
</select>
```

---

## 🛡 주의사항

- OpenAI API 사용량이 발생하므로 변환 쿼리 수에 따라 비용이 부과됩니다.
- CDATA 태그와 이스케이프 문자는 원본 구조를 최대한 보존하도록 설계되어 있습니다.
- 대용량 XML 변환 시 OpenAI API 제한에 유의하세요.

---

## 📜 라이선스

MIT License
