# 로그인(선택)과 내 계정 저장 설정하기

PaperPath의 로그인은 **선택 기능**입니다. 아래 설정이 하나라도 없으면 로그인 버튼이 보이지 않고, 지금처럼
이 브라우저 저장(A)·결과 파일(B)만으로 동작합니다. 설정은 이의상이 직접 하고, 키 값은 저장소에 넣지 않습니다.

- 로그인: Google 계정(Streamlit `st.login`, OpenID Connect)
- 저장소: Supabase(무료 Postgres). 사용자별로 번역·뜻 풀이 결과와 '다시 열 문서'(절 글자)를 저장
- 저장하지 않는 것: 이메일·이름(로그인 ID를 비밀 소금과 섞은 해시로만 구분), PDF 파일, 표·그림 이미지

## 1. Supabase 만들기 (약 10분)

1. [supabase.com](https://supabase.com)에 가입하고 **New project**를 만듭니다. 지역은 Northeast Asia(Seoul)를 고르면 빠릅니다.
2. 왼쪽 **SQL Editor**에서 아래를 붙여 넣고 **Run**을 누릅니다.

```sql
create table if not exists paperpath_items (
  user_id text not null,
  text_hash text not null,
  item jsonb not null,
  updated_at timestamptz not null default now(),
  primary key (user_id, text_hash)
);
create table if not exists paperpath_docs (
  user_id text not null,
  doc_id text not null,
  doc jsonb not null,
  updated_at timestamptz not null default now(),
  primary key (user_id, doc_id)
);
-- 행 수준 보안을 켜고 정책은 두지 않는다: 공개 키(anon)로는 읽지도 쓰지도 못하고, 서버 전용 키로만 접근한다
alter table paperpath_items enable row level security;
alter table paperpath_docs enable row level security;

-- 사용자별 하루 번역 기록(하루 새 논문 1편 한도, src/quota.py)
create table if not exists paperpath_usage (
  user_id text not null,
  day text not null,
  usage jsonb not null,
  primary key (user_id, day)
);
alter table paperpath_usage enable row level security;
```

이미 앞의 두 테이블을 만들었다면 `paperpath_usage` 부분만 한 번 더 실행하면 됩니다.

3. **Project Settings → API Keys**에서 두 값을 적어 둡니다.
   - Project URL: `https://xxxx.supabase.co` (Data API 메뉴에 있음)
   - **secret** 키(`sb_secret_…`) 또는 예전 화면의 **service_role** 키. 이 키는 서버 전용이라 화면·저장소에 절대 넣지 않습니다.

무료 프로젝트는 1주일 동안 쓰지 않으면 일시 정지될 수 있습니다. 발표 전에 Supabase 대시보드에서 상태를 확인하세요.

## 2. Google 로그인 앱 만들기 (약 15분)

1. [console.cloud.google.com](https://console.cloud.google.com)에서 새 프로젝트(예: PaperPath)를 만듭니다.
2. **API 및 서비스 → OAuth 동의 화면**(Google Auth Platform)
   - 사용자 유형: **외부**, 앱 이름: PaperPath, 지원 이메일: 본인
   - 범위는 기본(openid, email, profile)만 씁니다.
   - **대상(게시 상태)**을 '프로덕션'으로 바꿔야 등록하지 않은 사람도 로그인할 수 있습니다. 기본 범위만 쓰면 보통 심사 없이 바뀌지만, 화면에서 확인이 필요합니다. 바꾸기 전에는 '테스트 사용자'에 넣은 계정(최대 100개)만 로그인됩니다.
3. **사용자 인증 정보 → 사용자 인증 정보 만들기 → OAuth 클라이언트 ID**
   - 애플리케이션 유형: **웹 애플리케이션**
   - 승인된 리디렉션 URI 두 개:
     - `https://paperpath-hufs.streamlit.app/oauth2callback`
     - `http://localhost:8501/oauth2callback` (내 PC에서 실행할 때)
4. 만들어진 **클라이언트 ID**와 **클라이언트 보안 비밀번호**를 적어 둡니다.

## 3. 비밀 문자열 두 개 만들기

터미널에서 아래를 두 번 실행해 나온 값을 각각 `cookie_secret`, `USER_ID_SALT`로 씁니다.

```bash
py -c "import secrets; print(secrets.token_urlsafe(32))"
```

`USER_ID_SALT`를 나중에 바꾸면 이미 저장된 기록을 찾을 수 없게 됩니다(사용자 키가 달라짐). 한 번 정하면 그대로 두세요.

## 4. Streamlit Cloud Secrets에 넣기

share.streamlit.io → 앱 → **Settings → Secrets**에 기존 키 아래로 붙이고 값을 채웁니다.

```toml
SUPABASE_URL = "https://xxxx.supabase.co"
SUPABASE_SERVICE_KEY = "sb_secret_..."
USER_ID_SALT = "3단계에서 만든 값 1"

[auth]
redirect_uri = "https://paperpath-hufs.streamlit.app/oauth2callback"
cookie_secret = "3단계에서 만든 값 2"
client_id = "....apps.googleusercontent.com"
client_secret = "..."
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
```

`[auth]` 아래 줄은 반드시 맨 마지막에 둡니다(TOML에서 `[auth]` 뒤의 줄은 모두 auth에 들어갑니다).
저장 후 앱이 다시 켜지면 오른쪽 위에 **로그인** 버튼이 생깁니다.

## 5. 내 PC에서 쓰려면

`.streamlit/secrets.toml`(커밋되지 않음, `.streamlit/secrets.toml.example` 참고)에 같은 내용을 넣되
`redirect_uri`를 `http://localhost:8501/oauth2callback`으로 바꾸고, 8501 포트로 실행합니다.

```bash
.venv/Scripts/python.exe -m streamlit run app.py --server.port 8501
```

## 확인 순서

1. 로그인 → PDF를 넣고 한 절 번역 → '저장된 문서'에 '로그인 중 … 내 계정에 저장' 안내가 보이는지
2. 다른 브라우저(또는 시크릿 창)에서 같은 계정으로 로그인 → '저장된 문서'에 그 논문이 있고, 다시 열면 번역이 API 호출 없이 보이는지
3. '내 계정에 저장된 기록 모두 지우기' → Supabase Table Editor에서 두 테이블의 내 행이 지워졌는지
