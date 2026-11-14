# 시아애비 블로그 자동작성기 자동 배포 준비

기존에 설치된 v18.1은 변경하지 않습니다.

## 목표
- 수정한 Python 소스가 GitHub main에 반영되면 GitHub Actions가 Windows에서 EXE를 빌드
- v18.1 업데이트 버튼이 기대하는 정확한 파일명 `siaaebi-update.zip`, `siaaebi-update.zip.sha256`으로 게시
- 사용자는 실행 중인 블로그 작성기의 **업데이트 확인** 버튼만 사용

## 완료하기 전에 필요한 작업
- 반드시 검토된 v18.2의 전체 `app.py`와 `exe_updater.py` 소스를 저장소에 추가
- 프로젝트가 처음에 README만 있던 저장소였으므로 빌드 성공 확인 전에는 새로운 Release를 만들지 않음
- 모든 소스는 고객 데이터, 개인사진, OpenAI API 키가 없는지 검토
- 첫 GitHub Actions Windows 빌드와 새 버전 작동 확인 후 실사용 배포

## 사용 방법
소스를 main에 반영하면 자동 빌드가 시작되며 동일 버전이 이미 있으면 재배포하지 않습니다. 버전은 `app.py`의 `APP_VERSION`으로 결정합니다.
