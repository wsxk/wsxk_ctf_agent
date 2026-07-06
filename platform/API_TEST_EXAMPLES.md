# API Test Examples

下面的样例覆盖 `API.md` 中的每个接口。启动服务后执行：

```powershell
python run.py --host 127.0.0.1 --port 8000 --pwn-port 9005 --reset-state
```

设置测试环境变量：

```powershell
$env:HWCTF_API_ENDPOINT = "http://127.0.0.1:8000/api/v1"
$env:HWCTF_AGENT_KEY = "local-agent-key"
```

## 1. 获取队伍信息

`GET /api/v1/agent/team/profile`

```powershell
curl.exe -s `
  -H "X-Agent-Key: $env:HWCTF_AGENT_KEY" `
  "$env:HWCTF_API_ENDPOINT/agent/team/profile"
```

## 2. 获取题目列表

`GET /api/v1/agent/challenges`

```powershell
curl.exe -s `
  -H "X-Agent-Key: $env:HWCTF_AGENT_KEY" `
  "$env:HWCTF_API_ENDPOINT/agent/challenges"
```

## 3. 获取 Web 题详情

`GET /api/v1/agent/challenges/<challenge_id>`

```powershell
curl.exe -s `
  -H "X-Agent-Key: $env:HWCTF_AGENT_KEY" `
  "$env:HWCTF_API_ENDPOINT/agent/challenges/101"
```

## 4. 获取 Pwn 题详情和附件地址

`GET /api/v1/agent/challenges/<challenge_id>`

```powershell
curl.exe -s `
  -H "X-Agent-Key: $env:HWCTF_AGENT_KEY" `
  "$env:HWCTF_API_ENDPOINT/agent/challenges/201"
```

## 5. 下载 Pwn 附件

`GET /api/v1/challenge-platform/files/<file_id>/download`

```powershell
curl.exe -L `
  -H "X-Agent-Key: $env:HWCTF_AGENT_KEY" `
  "$env:HWCTF_API_ENDPOINT/challenge-platform/files/9/download" `
  -o pwn-echo.txt

curl.exe -L `
  -H "X-Agent-Key: $env:HWCTF_AGENT_KEY" `
  "$env:HWCTF_API_ENDPOINT/challenge-platform/files/10/download" `
  -o libc.so.6.txt
```

## 6. 查看当前环境列表

`GET /api/v1/agent/env`

```powershell
curl.exe -s `
  -H "X-Agent-Key: $env:HWCTF_AGENT_KEY" `
  "$env:HWCTF_API_ENDPOINT/agent/env"
```

## 7. 查看单题环境状态

`GET /api/v1/agent/challenges/<challenge_id>/env`

```powershell
curl.exe -s `
  -H "X-Agent-Key: $env:HWCTF_AGENT_KEY" `
  "$env:HWCTF_API_ENDPOINT/agent/challenges/101/env"
```

## 8. 启动 Web 动态环境

`POST /api/v1/agent/challenges/<challenge_id>/env`

```powershell
$webEnvResponse = curl.exe -s -X POST `
  -H "X-Agent-Key: $env:HWCTF_AGENT_KEY" `
  "$env:HWCTF_API_ENDPOINT/agent/challenges/101/env" | ConvertFrom-Json

$webEnv = $webEnvResponse.data.env
$webEnv
```

访问返回的 Web 环境：

```powershell
curl.exe -s `
  -H "X-Agent-Key: $env:HWCTF_AGENT_KEY" `
  $webEnv.url
```

## 9. 关闭动态环境

`DELETE /api/v1/agent/env/<env_id>`

```powershell
curl.exe -s -X DELETE `
  -H "X-Agent-Key: $env:HWCTF_AGENT_KEY" `
  "$env:HWCTF_API_ENDPOINT/agent/env/$($webEnv.external_env_id)"
```

## 10. 解锁提示

`POST /api/v1/agent/challenges/<challenge_id>/hints/<hint_id>/unlock`

```powershell
curl.exe -s -X POST `
  -H "X-Agent-Key: $env:HWCTF_AGENT_KEY" `
  "$env:HWCTF_API_ENDPOINT/agent/challenges/101/hints/1/unlock"
```

## 11. 提交错误 Flag

`POST /api/v1/agent/challenges/<challenge_id>/submit`

```powershell
curl.exe -s -X POST `
  -H "X-Agent-Key: $env:HWCTF_AGENT_KEY" `
  -H "Content-Type: application/json" `
  -d '{"flag":"FLAG{wrong}"}' `
  "$env:HWCTF_API_ENDPOINT/agent/challenges/101/submit"
```

## 12. 提交正确 Flag

`POST /api/v1/agent/challenges/<challenge_id>/submit`

```powershell
curl.exe -s -X POST `
  -H "X-Agent-Key: $env:HWCTF_AGENT_KEY" `
  -H "Content-Type: application/json" `
  -d '{"flag":"FLAG{web_login_admin}"}' `
  "$env:HWCTF_API_ENDPOINT/agent/challenges/101/submit"
```

多 Flag 题继续提交第二个 Flag：

```powershell
curl.exe -s -X POST `
  -H "X-Agent-Key: $env:HWCTF_AGENT_KEY" `
  -H "Content-Type: application/json" `
  -d '{"flag":"FLAG{web_debug_backup}"}' `
  "$env:HWCTF_API_ENDPOINT/agent/challenges/101/submit"
```

## 13. 启动 Pwn 动态环境

`POST /api/v1/agent/challenges/<challenge_id>/env`

```powershell
$pwnEnvResponse = curl.exe -s -X POST `
  -H "X-Agent-Key: $env:HWCTF_AGENT_KEY" `
  "$env:HWCTF_API_ENDPOINT/agent/challenges/201/env" | ConvertFrom-Json

$pwnEnv = $pwnEnvResponse.data.env
$pwnEnv
```

使用 Python socket 访问 Pwn Gateway：

```powershell
python -c "import socket,sys; h='$($pwnEnv.routing_header)'; s=socket.create_connection(('$($pwnEnv.host)', int('$($pwnEnv.port)')), timeout=5); print(s.recv(4096).decode(errors='ignore')); s.sendall((h+'\n').encode()); s.sendall(b'help\nflag\nexit\n'); print(s.recv(4096).decode(errors='ignore')); s.close()"
```

关闭 Pwn 环境：

```powershell
curl.exe -s -X DELETE `
  -H "X-Agent-Key: $env:HWCTF_AGENT_KEY" `
  "$env:HWCTF_API_ENDPOINT/agent/env/$($pwnEnv.external_env_id)"
```

## 14. 获取排行榜

`GET /api/v1/agent/scoreboard`

```powershell
curl.exe -s `
  -H "X-Agent-Key: $env:HWCTF_AGENT_KEY" `
  "$env:HWCTF_API_ENDPOINT/agent/scoreboard"
```

## 15. 认证失败样例

所有 Agent 接口缺少或错误 `X-Agent-Key` 时返回 `unauthorized`：

```powershell
curl.exe -s `
  -H "X-Agent-Key: wrong-key" `
  "$env:HWCTF_API_ENDPOINT/agent/team/profile"
```

## 一键执行所有请求样例

```powershell
python scripts/api_request_examples.py
```
