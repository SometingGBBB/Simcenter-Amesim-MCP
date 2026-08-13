# amesim-mcp

An [MCP](https://modelcontextprotocol.io) server that exposes Siemens Simcenter
Amesim's Circuit API as tools for Claude (Desktop or Code) — build circuits,
wire components, set parameters, compile, run simulations, and read back
results, all from a chat.

> Unofficial, independent project. Not affiliated with or endorsed by
> Siemens. "Simcenter Amesim" is a Siemens trademark.

## How it works

Amesim's Python API only exists inside `AMEPython.exe`, an embedded Python
3.6 interpreter shipped with Amesim. Two problems rule out just running the
MCP server directly under `AMEPython.exe`:

1. `AMEPython.exe` prints an unconditional `Starting Python ...` banner to
   stdout with no way to silence it — which would corrupt the JSON-RPC
   stream an MCP stdio server needs.
2. `AMERunSimulation` (and apparently other run-management calls) hangs
   forever when invoked from any thread other than the process's main
   thread. Siemens' own `scripting/python/serve_api.py` example serves
   RPyC connections on background threads (`ThreadedServer`), so it hits
   this hang too.

So this project splits into two processes:

- **MCP server** (`amesim_mcp/server.py`) — a normal Python 3.12+ process,
  the one Claude talks to over stdio.
- **Worker** (`amesim_mcp/worker_entry.py`) — spawned inside
  `AMEPython.exe`, running an [RPyC](https://rpyc.readthedocs.io/)
  `OneShotServer` (single connection, served synchronously on the main
  thread — this is what avoids the hang). Its stdout/stderr (banner
  included) is redirected to `amesim_worker.log`, never touching the MCP
  server's own stdio.

The MCP server talks to the worker as an ordinary RPyC client over a local
TCP port (default `18861`).

Because `AMEPython.exe`'s embedded interpreter has no `pip`/internet
access, `vendor/` bundles pre-built copies of the packages the worker
needs (`pywin32`, `rpyc`, `plumbum`, `adodbapi`) — see
[NOTICE.md](NOTICE.md) for their original licenses. The worker process gets
`vendor/` prepended to its `PYTHONPATH` when spawned.

## Requirements

- Windows, with Simcenter Amesim installed (2021.1 and 2404 are configured
  by default — see below to add/change a version).
- Python 3.12+ on your normal system Python (separate from Amesim's
  embedded 3.6) to run the MCP server itself.
- Claude Desktop or Claude Code (or any other MCP-compatible client).

## Install

```bash
git clone <this-repo-url>
cd amesim-mcp
py -3.13 -m pip install -e .
```

(Any Python ≥3.12 works — `py -3.13` is just what was used to develop
this.)

If your Amesim install lives somewhere other than
`C:\Program Files\Simcenter\<version>\Amesim`, or you use a version other
than 2021.1 / 2404, edit `VERSION_DIRS` in
[`amesim_mcp/amesim_api.py`](amesim_mcp/amesim_api.py):

```python
VERSION_DIRS = {
    "2021.1": r"C:\Program Files\Simcenter\2021.1\Amesim",
    "2404": r"C:\Program Files\Simcenter\2404\Amesim",
}
```

## Configure your MCP client

**Claude Desktop** — add to `%APPDATA%\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "amesim": {
      "command": "py",
      "args": ["-3.13", "-m", "amesim_mcp.server"]
    }
  }
}
```

**Claude Code / other project-scoped MCP clients** — copy the example and
edit the path:

```bash
cp .mcp.json.example .mcp.json
```

```json
{
  "mcpServers": {
    "amesim": {
      "command": "python",
      "args": ["-m", "amesim_mcp.server"],
      "cwd": "C:/path/to/amesim-mcp"
    }
  }
}
```

`.mcp.json` is machine-specific (absolute path) and is gitignored — don't
commit it.

## Usage

A typical session:

```
connect → create_circuit → add_component → change_submodel →
connect_two_ports → set_parameter_value → generate_code →
run_simulation → get_variable_values → save_circuit → disconnect
```

| Tool | Purpose |
|---|---|
| `connect(version)` | Start/attach to the Amesim worker ("2021.1" or "2404") |
| `disconnect()` | Release the license token, stop the worker |
| `status()` | Connection state + Circuit API version |
| `execute_python(code)` | Run arbitrary Python in the worker's persistent namespace — `ame_apy` and `amesim` are pre-imported. Use this for anything without a dedicated tool, and to look up exact signatures with `execute_python("help(ame_apy.SOME_FUNCTION)")` |
| `create_circuit(name)` | Create a new circuit |
| `open_ame_file(path)` | Open an existing `.ame` file |
| `save_circuit()` | Save the active circuit |
| `close_circuit(save)` | Close the active circuit |
| `add_component(icon_name, alias, x, y)` | Add a component to the sketch |
| `move_component(alias, x, y)` | Move a component |
| `rotate_component(alias, quarter_turns)` | Rotate a component |
| `flip_component(alias)` | Mirror a component |
| `remove_component(alias)` | Remove a component |
| `connect_two_ports(alias1, port1, alias2, port2)` | Wire two ports together |
| `remove_line(alias)` | Remove a connection line |
| `create_supercomponent(...)` | Group components into a reusable sub-circuit |
| `change_submodel(alias, submodel_name, submodel_path)` | Assign a submodel |
| `get_parameter_value(data_path)` / `set_parameter_value(data_path, value)` | Read/write a parameter or state's initial value |
| `get_parameter_infos(data_path)` | Type, title, unit of a parameter |
| `generate_code()` | Compile the active circuit |
| `set_run_parameter(name, value)` | Set a run/simulation parameter |
| `run_simulation()` | Run a temporal simulation |
| `get_variable_values(data_path)` | Time-series `[time, value]` pairs from the last run |
| `get_variable_infos(data_path)` | Metadata about a variable |

`connect()` checks out one Amesim license token for the whole session —
call `disconnect()` when done so it doesn't block your own interactive
Amesim usage.

## Troubleshooting

- **"AMEPython.exe not found for version ..."** — `VERSION_DIRS` in
  `amesim_api.py` doesn't match where Amesim is actually installed on
  your machine.
- **Worker seems to hang or crash silently** — check
  `amesim_worker.log` in the project root; the worker's stdout/stderr
  (including any Amesim-side traceback) lands there.
- **Stuck holding a license token** — call `disconnect()`, or kill the
  `AMEPython.exe` process directly if the MCP server itself is gone.

## License

MIT for `amesim_mcp/` — see [LICENSE](LICENSE). `vendor/` bundles
third-party packages under their own licenses — see [NOTICE.md](NOTICE.md).

---

# amesim-mcp (한국어)

[MCP](https://modelcontextprotocol.io) 프로토콜로 Siemens Simcenter Amesim의
Circuit API를 Claude(Desktop/Code)의 도구로 노출하는 서버입니다. 채팅만으로
회로를 만들고, 컴포넌트를 배치·연결하고, 파라미터를 설정하고, 컴파일·시뮬레이션을
실행하고, 결과를 읽어올 수 있습니다.

> 비공식 개인 프로젝트이며 Siemens와 아무런 제휴·후원 관계가 없습니다.
> "Simcenter Amesim"은 Siemens의 상표입니다.

## 동작 원리

Amesim의 Python API는 Amesim에 내장된 Python 3.6 인터프리터인
`AMEPython.exe` 안에서만 존재합니다. MCP 서버를 `AMEPython.exe` 위에서
그대로 돌릴 수 없는 이유가 두 가지 있습니다.

1. `AMEPython.exe`는 시작할 때 `Starting Python ...` 배너를 표준출력으로
   무조건 출력하며 끌 방법이 없습니다. MCP stdio 서버가 이 프로세스로
   그대로 동작하면 이 배너가 JSON-RPC 스트림을 깨뜨립니다.
2. `AMERunSimulation`(및 다른 실행 관련 API로 보이는 함수들)은 메인 스레드가
   아닌 다른 스레드에서 호출하면 무한정 멈춥니다. Siemens가 제공하는
   `scripting/python/serve_api.py` 예제는 RPyC 연결을 백그라운드 스레드에서
   처리하는 `ThreadedServer`를 쓰기 때문에 그대로 쓰면 이 문제를 그대로
   겪습니다.

그래서 이 프로젝트는 프로세스를 두 개로 나눕니다.

- **MCP 서버** (`amesim_mcp/server.py`) — 일반 Python 3.12+ 프로세스로,
  Claude와 stdio로 통신합니다.
- **워커(worker)** (`amesim_mcp/worker_entry.py`) — `AMEPython.exe` 안에서
  실행되며, [RPyC](https://rpyc.readthedocs.io/)의 `OneShotServer`(연결
  1개만, 메인 스레드에서 동기적으로 처리 — 이게 바로 위 hang 문제를
  피하는 방법입니다)를 띄웁니다. 이 워커의 표준출력/에러(배너 포함)는
  `amesim_worker.log`로 리다이렉트되어 MCP 서버 자신의 stdio에는 절대
  섞이지 않습니다.

MCP 서버는 로컬 TCP 포트(기본값 `18861`)로 이 워커에 일반적인 RPyC
클라이언트처럼 접속합니다.

`AMEPython.exe`의 내장 인터프리터는 `pip`도, 인터넷 접근도 안 되기 때문에
워커가 필요로 하는 패키지들(`pywin32`, `rpyc`, `plumbum`, `adodbapi`)의
빌드된 사본을 `vendor/`에 함께 담아두었습니다 (각 패키지의 원 라이선스는
[NOTICE.md](NOTICE.md) 참고). 워커 프로세스를 띄울 때 `vendor/`가
`PYTHONPATH` 맨 앞에 추가됩니다.

## 요구 사항

- Windows, Simcenter Amesim 설치 (기본 설정은 2021.1과 2404 — 다른
  버전/경로를 쓰려면 아래 참고).
- MCP 서버 자체를 돌릴 Python 3.12+ (Amesim에 내장된 3.6과는 별개의,
  시스템에 설치된 일반 Python).
- Claude Desktop 또는 Claude Code (다른 MCP 호환 클라이언트도 가능).

## 설치

```bash
git clone <이 저장소 URL>
cd amesim-mcp
py -3.13 -m pip install -e .
```

(3.12 이상이면 어떤 Python이든 됩니다 — `py -3.13`은 개발할 때 쓴 버전일
뿐입니다.)

Amesim이 `C:\Program Files\Simcenter\<버전>\Amesim`이 아닌 다른 경로에
설치되어 있거나, 2021.1 / 2404가 아닌 다른 버전을 쓴다면
[`amesim_mcp/amesim_api.py`](amesim_mcp/amesim_api.py)의 `VERSION_DIRS`를
수정하세요.

```python
VERSION_DIRS = {
    "2021.1": r"C:\Program Files\Simcenter\2021.1\Amesim",
    "2404": r"C:\Program Files\Simcenter\2404\Amesim",
}
```

## MCP 클라이언트 설정

**Claude Desktop** — `%APPDATA%\Claude\claude_desktop_config.json`에 추가:

```json
{
  "mcpServers": {
    "amesim": {
      "command": "py",
      "args": ["-3.13", "-m", "amesim_mcp.server"]
    }
  }
}
```

**Claude Code 등 프로젝트 단위 MCP 클라이언트** — 예제 파일을 복사해서
경로만 바꿔주세요.

```bash
cp .mcp.json.example .mcp.json
```

```json
{
  "mcpServers": {
    "amesim": {
      "command": "python",
      "args": ["-m", "amesim_mcp.server"],
      "cwd": "C:/path/to/amesim-mcp"
    }
  }
}
```

`.mcp.json`은 절대경로가 들어가는 개인 환경 설정 파일이라 `.gitignore`에
포함되어 있습니다 — 커밋하지 마세요.

## 사용법

일반적인 사용 흐름:

```
connect → create_circuit → add_component → change_submodel →
connect_two_ports → set_parameter_value → generate_code →
run_simulation → get_variable_values → save_circuit → disconnect
```

| 도구 | 설명 |
|---|---|
| `connect(version)` | Amesim 워커 시작/연결 ("2021.1" 또는 "2404") |
| `disconnect()` | 라이선스 토큰 반납, 워커 종료 |
| `status()` | 연결 상태 + Circuit API 버전 확인 |
| `execute_python(code)` | 워커의 지속되는(persistent) 네임스페이스에서 임의 Python 코드 실행 — `ame_apy`, `amesim`이 이미 import되어 있음. 전용 도구가 없는 작업이나, `execute_python("help(ame_apy.함수이름)")`으로 정확한 시그니처를 확인할 때 사용 |
| `create_circuit(name)` | 새 회로 생성 |
| `open_ame_file(path)` | 기존 `.ame` 파일 열기 |
| `save_circuit()` | 현재 회로 저장 |
| `close_circuit(save)` | 현재 회로 닫기 |
| `add_component(icon_name, alias, x, y)` | 스케치에 컴포넌트 추가 |
| `move_component(alias, x, y)` | 컴포넌트 이동 |
| `rotate_component(alias, quarter_turns)` | 컴포넌트 회전 |
| `flip_component(alias)` | 컴포넌트 좌우 반전 |
| `remove_component(alias)` | 컴포넌트 삭제 |
| `connect_two_ports(alias1, port1, alias2, port2)` | 두 포트를 선으로 연결 |
| `remove_line(alias)` | 연결선 삭제 |
| `create_supercomponent(...)` | 컴포넌트들을 재사용 가능한 슈퍼컴포넌트로 묶기 |
| `change_submodel(alias, submodel_name, submodel_path)` | 서브모델 지정 |
| `get_parameter_value(data_path)` / `set_parameter_value(data_path, value)` | 파라미터/초기 상태값 읽기·쓰기 |
| `get_parameter_infos(data_path)` | 파라미터의 타입/제목/단위 조회 |
| `generate_code()` | 현재 회로 컴파일 |
| `set_run_parameter(name, value)` | 실행/시뮬레이션 파라미터 설정 |
| `run_simulation()` | 시간 영역 시뮬레이션 실행 |
| `get_variable_values(data_path)` | 마지막 실행의 `[time, value]` 시계열 값 |
| `get_variable_infos(data_path)` | 변수 메타데이터 조회 |

`connect()`는 세션 동안 Amesim 라이선스 토큰을 하나 점유합니다. 다 쓰면
`disconnect()`를 호출해서 본인의 대화형 Amesim 사용을 막지 않도록 하세요.

## 문제 해결

- **"AMEPython.exe not found for version ..."** — `amesim_api.py`의
  `VERSION_DIRS` 경로가 실제 설치 경로와 다릅니다.
- **워커가 멈춘 것 같거나 조용히 죽는 경우** — 프로젝트 루트의
  `amesim_worker.log`를 확인하세요. 워커의 표준출력/에러(Amesim 쪽
  트레이스백 포함)가 여기 남습니다.
- **라이선스 토큰을 반납하지 못하고 물려있는 경우** — `disconnect()`를
  호출하거나, MCP 서버 자체가 죽었다면 `AMEPython.exe` 프로세스를 직접
  종료하세요.

## 라이선스

`amesim_mcp/`는 MIT 라이선스입니다 — [LICENSE](LICENSE) 참고. `vendor/`는
각 패키지의 원 라이선스를 그대로 유지합니다 — [NOTICE.md](NOTICE.md) 참고.
