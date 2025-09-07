# 문서 자동 업데이트 프로세스

이 문서는 소스 코드 변경 시 관련 문서를 자동으로 업데이트하는 프로세스를 정의합니다.

## 📋 개요

소스 코드의 변경사항이 성공적으로 처리되면, 관련 문서들을 자동으로 업데이트하여 코드와 문서 간의 일관성을 유지합니다.

## 🔄 자동 업데이트 프로세스

### 1. 변경사항 감지 및 분석

#### 1.1. 스테이징된 파일 분석
```bash
# Git 스테이징 영역의 변경사항 확인
git diff --cached --name-only

# 주요 변경 파일 유형별 분류
- src/plugin/connector/*.py     → 커넥터 관련 문서 업데이트
- src/plugin/manager/*.py       → 매니저 관련 문서 업데이트  
- src/plugin/parser/*.py        → 파서 관련 문서 업데이트
- src/plugin/conf/*.py          → 설정 관련 문서 업데이트
```

#### 1.2. 변경사항 유형 분류
- **신규 기능 추가**: 새로운 클래스, 메서드, 기능
- **기능 개선**: 기존 기능의 향상 및 확장
- **버그 수정**: 오류 수정 및 안정성 개선
- **성능 최적화**: 성능 향상 및 리소스 효율성 개선

### 2. 문서 업데이트 대상 결정

#### 2.1. 핵심 문서 매핑
| 소스 파일 | 업데이트 대상 문서 |
|:---------|:------------------|
| `connector/*.py` | `docs/ko/technical/architecture.md` |
| `manager/*.py` | `docs/ko/technical/architecture.md` |
| `parser/*.py` | `docs/ko/technical/data-models.md` |
| 신규 기능 | `docs/ko/development/implementation-roadmap.md` |
| API 변경 | `docs/ko/technical/api-specifications.md` |
| 사용자 기능 | `docs/ko/user-guide/*.md` |

#### 2.2. 업데이트 우선순위
1. **High Priority**: 아키텍처, API 명세, 구현 로드맵
2. **Medium Priority**: 사용자 가이드, 기술 문서
3. **Low Priority**: 예시, 튜토리얼, FAQ

### 3. 자동 업데이트 실행

#### 3.1. 아키텍처 문서 업데이트
```markdown
# docs/ko/technical/architecture.md 업데이트 항목
- 새로운 커넥터/매니저 추가 시 컴포넌트 설명 업데이트
- 기능 개선 시 해당 컴포넌트의 기능 목록 업데이트
- 데이터 플로우 변경 시 플로우 다이어그램 수정
```

#### 3.2. 구현 로드맵 업데이트
```markdown
# docs/ko/development/implementation-roadmap.md 업데이트 항목
- 완료된 기능을 "✅ 최근 완료" 섹션에 추가
- 버전 정보 및 완료 날짜 기록
- 상세 구현 내용 및 주요 특징 설명
```

#### 3.3. 사용자 가이드 업데이트
```markdown
# docs/ko/user-guide/*.md 업데이트 항목
- 새로운 설정 옵션 추가 시 설정 가이드 업데이트
- 새로운 기능 추가 시 사용법 예시 추가
- API 변경 시 호출 방법 및 응답 형식 업데이트
```

## 🛠️ 구현 가이드

### 1. 변경사항 분석 스크립트

#### 1.1. 파일 변경 감지
```python
import subprocess
import os
from typing import List, Dict

def get_staged_changes() -> List[str]:
    """스테이징된 파일 목록 반환"""
    result = subprocess.run(
        ['git', 'diff', '--cached', '--name-only'], 
        capture_output=True, text=True
    )
    return result.stdout.strip().split('\n') if result.stdout.strip() else []

def analyze_changes(files: List[str]) -> Dict[str, List[str]]:
    """변경된 파일을 카테고리별로 분류"""
    categories = {
        'connectors': [],
        'managers': [],
        'parsers': [],
        'configs': [],
        'tests': []
    }
    
    for file in files:
        if 'connector/' in file and file.endswith('.py'):
            categories['connectors'].append(file)
        elif 'manager/' in file and file.endswith('.py'):
            categories['managers'].append(file)
        elif 'parser/' in file and file.endswith('.py'):
            categories['parsers'].append(file)
        elif 'conf/' in file and file.endswith('.py'):
            categories['configs'].append(file)
        elif 'test/' in file and file.endswith('.py'):
            categories['tests'].append(file)
    
    return categories
```

#### 1.2. 문서 업데이트 로직
```python
def update_architecture_doc(changes: Dict[str, List[str]]) -> None:
    """아키텍처 문서 자동 업데이트"""
    doc_path = "docs/ko/technical/architecture.md"
    
    # 커넥터 변경사항 반영
    if changes['connectors']:
        update_connector_section(doc_path, changes['connectors'])
    
    # 매니저 변경사항 반영
    if changes['managers']:
        update_manager_section(doc_path, changes['managers'])

def update_roadmap_doc(version: str, features: List[str]) -> None:
    """구현 로드맵 문서 자동 업데이트"""
    doc_path = "docs/ko/development/implementation-roadmap.md"
    
    # 새로운 완료 섹션 추가
    completed_section = f"""
### ✅ 최근 완료 (v{version})
{chr(10).join(f"{i+1}. ✅ **{feature}**" for i, feature in enumerate(features))}
"""
    
    # 기존 문서에 섹션 삽입
    insert_completed_section(doc_path, completed_section)
```

### 2. 자동화 워크플로우

#### 2.1. Git Hook 활용
```bash
#!/bin/sh
# .git/hooks/pre-commit

# 스테이징된 변경사항 분석
python scripts/analyze_changes.py

# 문서 업데이트 실행
python scripts/update_docs.py

# 업데이트된 문서를 스테이징에 추가
git add docs/
```

#### 2.2. CI/CD 통합
```yaml
# .github/workflows/doc-update.yml
name: Auto Documentation Update

on:
  push:
    branches: [ main, develop ]
    paths: [ 'src/**/*.py' ]

jobs:
  update-docs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Analyze Changes
        run: python scripts/analyze_changes.py
        
      - name: Update Documentation
        run: python scripts/update_docs.py
        
      - name: Commit Updated Docs
        run: |
          git config --local user.email "action@github.com"
          git config --local user.name "GitHub Action"
          git add docs/
          git diff --staged --quiet || git commit -m "docs: Auto-update documentation"
          git push
```

## 📝 업데이트 템플릿

### 1. 신규 커넥터 추가 시

```markdown
- **{ConnectorName}**: {기능 설명} (✅ 구현 완료)
  - {주요 기능 1}
  - {주요 기능 2}
  - {주요 기능 3}
```

### 2. 기능 개선 시

```markdown
- **{ComponentName}**: {기능 설명} (✅ 향상됨)
  - {개선된 기능 1}
  - {개선된 기능 2}
  - {새로 추가된 기능}
```

### 3. 완료 항목 추가 시

```markdown
### ✅ 최근 완료 (v{version})
1. ✅ **{기능명}**: {상세 설명}
   - {구현 내용 1}
   - {구현 내용 2}
   - {구현 내용 3}
```

## 🔍 품질 보증

### 1. 문서 일관성 검증
- 링크 유효성 검사
- 마크다운 문법 검증
- 코드 블록 구문 검사

### 2. 내용 정확성 검증
- 코드와 문서 간 일치성 확인
- API 명세와 실제 구현 비교
- 예시 코드 실행 가능성 검증

### 3. 자동 테스트
```python
def test_documentation_consistency():
    """문서와 코드 간 일관성 테스트"""
    # 문서에 언급된 클래스/메서드가 실제 존재하는지 확인
    # API 문서의 파라미터가 실제 구현과 일치하는지 확인
    # 예시 코드가 실행 가능한지 확인
    pass
```

## 📊 모니터링 및 리포팅

### 1. 업데이트 통계
- 자동 업데이트된 문서 수
- 수동 개입이 필요한 항목 수
- 업데이트 성공률

### 2. 품질 메트릭
- 문서-코드 일치율
- 링크 유효성 비율
- 사용자 피드백 점수

## 🎯 향후 개선 방향

### 1. AI 기반 문서 생성
- 코드 변경사항을 자동으로 분석하여 문서 초안 생성
- 자연어 처리를 통한 더 정확한 설명 생성

### 2. 실시간 문서 동기화
- 코드 변경 시 실시간으로 관련 문서 업데이트
- 개발자에게 문서 업데이트 알림 제공

### 3. 다국어 문서 지원
- 한국어 문서 업데이트 시 영어 문서도 자동 번역 및 업데이트
- 언어별 문서 일관성 유지

---

> **참고**: 이 프로세스는 지속적으로 개선되며, 프로젝트의 성장에 따라 업데이트됩니다.
