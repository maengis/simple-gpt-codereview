# Simple GPT Code Review

OpenAI GPT 모델을 사용하여 Pull Request의 변경 사항을 자동으로 분석하고 코드 리뷰 코멘트를 생성하는 GitHub Action입니다.

## 기능

- Pull Request 이벤트 시 자동 실행
- OpenAI Responses API를 사용한 AI 코드 분석
- 변경된 코드 라인별 구체적인 리뷰 코멘트 제공
- 한국어로 리뷰 코멘트 생성
- Diff 기반 컨텍스트 분석으로 정확한 리뷰 제공
- Docker 컨테이너로 실행되는 격리된 환경

## 사용 방법

### 1. Repository Secrets 설정

대상 저장소의 **Settings > Secrets and variables > Actions**에서 다음 Secret을 추가하세요:

| Secret 이름 | 설명 | 필수 여부 |
|-------------|------|-----------|
| `OPENAI_KEY` | OpenAI API 인증키 | 필수 |

#### OpenAI API 키 발급 방법:
1. [OpenAI Platform](https://platform.openai.com/)에 로그인
2. **API Keys** 메뉴로 이동
3. **Create new secret key** 클릭
4. 생성된 키를 복사하여 GitHub Repository Secrets에 저장

### 2. Repository Variables 설정 (선택사항)

**Settings > Secrets and variables > Actions > Variables**에서 다음 변수를 설정할 수 있습니다:

| Variable 이름 | 기본값 | 설명 |
|---------------|--------|------|
| `OPENAI_MODEL` | `gpt-5-mini` | 사용할 OpenAI 모델 |

### 3. Workflow 파일 생성

대상 저장소의 `.github/workflows/` 디렉토리에 워크플로우 파일을 생성하세요:

#### 기본 사용 예시

```yaml
name: Simple GPT Code Review

on:
  pull_request:
    types: [opened, reopened, ready_for_review, synchronize]

jobs:
  code-review:
    if: ${{ github.event.sender.type != 'Bot' }}
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
    
    steps:
      - name: Simple GPT Code Review
        uses: maengis/simple-gpt-codereview@main
        with:
          OPENAI_KEY: ${{ secrets.OPENAI_KEY }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          OPENAI_MODEL: ${{ vars.OPENAI_MODEL || 'gpt-5-mini' }}
```

#### Self-hosted Runner 사용

```yaml
name: Simple GPT Code Review

on:
  pull_request:
    types: [opened, reopened, ready_for_review, synchronize]

jobs:
  code-review:
    if: ${{ github.event.sender.type != 'Bot' }}
    runs-on: [self-hosted, your-label]
    permissions:
      contents: read
      pull-requests: write
    
    steps:
      - name: Simple GPT Code Review
        uses: maengis/simple-gpt-codereview@main
        with:
          OPENAI_KEY: ${{ secrets.OPENAI_API_KEY }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          OPENAI_MODEL: 'gpt-5-mini'
```

#### 특정 파일만 리뷰하기

```yaml
name: Simple GPT Code Review

on:
  pull_request:
    types: [opened, reopened, ready_for_review, synchronize]
    paths:
      - '**.py'
      - '**.js'
      - '**.ts'
      - '**.java'

jobs:
  code-review:
    if: ${{ github.event.sender.type != 'Bot' }}
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
    
    steps:
      - name: Simple GPT Code Review
        uses: maengis/simple-gpt-codereview@main
        with:
          OPENAI_KEY: ${{ secrets.OPENAI_KEY }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          OPENAI_MODEL: ${{ vars.OPENAI_MODEL || 'gpt-5-mini' }}
```

### 4. 권한 설정

워크플로우에 다음 권한이 필요합니다:

```yaml
permissions:
  contents: read        # 저장소 코드 읽기
  pull-requests: write  # PR에 리뷰 코멘트 작성
```

## 설정 옵션

### 필수 입력값

| 파라미터 | 설명 | 예시 |
|----------|------|------|
| `OPENAI_KEY` | OpenAI API 키 | `${{ secrets.OPENAI_KEY }}` |
| `GITHUB_TOKEN` | GitHub API 토큰 | `${{ secrets.GITHUB_TOKEN }}` |
| `OPENAI_MODEL` | 사용할 OpenAI 모델 | `gpt-5-mini` |

## 동작 원리

1. **이벤트 감지**: PR이 열리거나 업데이트될 때 자동 실행
2. **변경 사항 분석**: GitHub API를 통해 변경된 파일과 diff 정보 수집
3. **코드 블록 추출**: 추가/삭제된 코드 블록을 컨텍스트와 함께 추출
4. **AI 분석**: 각 코드 블록을 OpenAI API로 전송하여 리뷰 생성
5. **리뷰 등록**: GitHub API를 통해 PR에 리뷰 코멘트 작성

## 리뷰 예시

AI가 생성하는 리뷰 코멘트 예시:

```
보안 관련 개선 제안:
- 사용자 입력값에 대한 검증이 누락되어 있습니다
- SQL 인젝션 공격에 취약할 수 있으니 파라미터화된 쿼리를 사용하세요

성능 최적화:
- 불필요한 반복문이 있습니다
- 캐싱을 고려해보세요

가독성 개선:
- 변수명을 더 명확하게 지정하면 좋겠습니다
- 주석을 추가하여 로직을 설명해주세요
```

## 커스터마이징

### 다른 언어로 리뷰받기

코드 내 `SYSTEM_PROMPT`를 수정하여 리뷰 언어를 변경할 수 있습니다:

```python
SYSTEM_PROMPT = (
    "You are a senior code reviewer. Provide concise, actionable review comments "
    "for each code change. Answer in English."
)
```

### 리뷰 스타일 변경

시스템 프롬프트를 수정하여 리뷰 스타일을 조정할 수 있습니다:

```python
SYSTEM_PROMPT = (
    "You are a friendly code mentor. Focus on teaching and explaining "
    "best practices. Be encouraging while providing constructive feedback."
)
```

1. **리뷰 범위 제한**:
   - 특정 파일 타입만 리뷰하도록 `paths` 필터 사용
   - 코드 스니펫 길이 제한 (`MAX_SNIPPET_CHARS = 2000`)

2. **사용량 모니터링**:
   - [OpenAI Usage Dashboard](https://platform.openai.com/usage)에서 사용량 확인

## 트러블슈팅

### 일반적인 오류

#### 1. "GITHUB_TOKEN env is required"
```yaml
# 해결방법: GITHUB_TOKEN을 with 섹션에 추가
with:
  GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

#### 2. "OPENAI_KEY env is required"
```yaml
# 해결방법: Repository Secrets에 OPENAI_KEY 추가 후
with:
  OPENAI_KEY: ${{ secrets.OPENAI_KEY }}
```

#### 3. "AI 호출 실패 [401]"
- OpenAI API 키가 유효한지 확인
- API 키에 충분한 크레딧이 있는지 확인

#### 4. "AI 호출 실패 [429]"
- OpenAI API 사용 한도 초과
- 잠시 후 재시도하거나 플랜 업그레이드 고려

### 디버깅 방법

1. **GitHub Actions 로그 확인**:
   - Actions 탭에서 실행 로그 확인
   - 각 단계별 상세 오류 메시지 검토

2. **API 키 테스트**:
   ```bash
   curl -H "Authorization: Bearer YOUR_API_KEY" \
        https://api.openai.com/v1/models
   ```

3. **권한 확인**:
   - Repository Settings > Actions > General
   - Workflow permissions가 "Read and write permissions"로 설정되어 있는지 확인

## 보안 고려사항

- OpenAI API 키는 반드시 Repository Secrets에 저장
- 코드 내용이 OpenAI 서버로 전송됨을 인지
- 민감한 정보가 포함된 저장소에서는 사용 주의
- GitHub Token은 GitHub Actions에서 자동 제공되는 안전한 토큰 사용

## 제한사항

- **처리 시간**: 대용량 PR의 경우 처리 시간이 길어질 수 있음
- **API 비용**: OpenAI API 사용량에 따른 과금 발생
- **컨텍스트 제한**: 최대 2000자까지의 코드 스니펫만 분석
- **언어 지원**: 모든 프로그래밍 언어를 지원하지만 일부 언어는 분석 품질이 다를 수 있음

## 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다.