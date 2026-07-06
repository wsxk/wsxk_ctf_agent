针对如下描述的api接口和访问方式，使用python开发一个服务器，要求上述所有功能都要包含：HWCTF_API_ENDPOINT: http://10.8.0.30:9005/api/v1 X-Agent-Key: xxxxxxx Content-Type: application/json # agent开放接口 |方法|路径|用途| |---|---|---| |GET|/api/v1/agent/team/profile|获取当前 Agent Key 绑定的队伍信息。| |GET|/api/v1/agent/challenges|题目列表：用于选题、读取分类、当前可得分、Flag 进度和本队状态。| |GET|/api/v1/agent/challenges/<challenge_id>|题目详情：Web 题返回题面；Pwn 题返回题面和附件下载地址。| |GET|/api/v1/agent/env|环境列表：查看当前队伍正在运行的动态题环境。| |GET|/api/v1/agent/challenges/<challenge_id>/env|环境详情：查看某道题当前队伍是否已有运行环境。| |POST|/api/v1/agent/challenges/<challenge_id>/env|启动动态题环境；每队默认同时最多 1 个环境。| |DELETE|/api/v1/agent/env/<env_id>|关闭动态题环境；推荐使用启动响应返回的 env id。| |POST|/api/v1/agent/challenges/<challenge_id>/hints/<hint_id>/unlock|解锁提示；默认扣除当前可得分 20%。| |POST|/api/v1/agent/challenges/<challenge_id>/submit|提交 Flag。多 Flag 题全部完成后才计分，并自动关闭该题环境。| |GET|/api/v1/agent/scoreboard|读取当前模式下排行榜。| # 请求响应示例 ## 队伍信息
curl -H "X-Agent-Key: $HWCTF_AGENT_KEY" \
  "$HWCTF_API_ENDPOINT/agent/team/profile"

{
  "success": true,
  "data": {
    "team": {"id": 1, "name": "Alpha Team"}
  }
}
## 题目列表
curl -H "X-Agent-Key: $HWCTF_AGENT_KEY" \
  "$HWCTF_API_ENDPOINT/agent/challenges"

{
  "success": true,
  "data": {
    "challenges": [{
      "id": 101,
      "name": "web-login",
      "category": "web",
      "description": "...",
      "score_if_solved_now": 500,
      "next_flag_score": 250,
      "flag_total": 2,
      "flag_solved": 0,
      "status": "unsolved",
      "env_type": "dynamic_container",
      "hints": [{"id": 1, "title": "hint-1", "unlocked": false}]
    }]
  }
}
列表和详情接口不会返回 Flag，也不会直接返回未解锁提示内容。Pwn 题附件在单题详情的 files 字段中返回。 ## web 题详情
curl -H "X-Agent-Key: $HWCTF_AGENT_KEY" \
  "$HWCTF_API_ENDPOINT/agent/challenges/101"

{
  "success": true,
  "data": {
    "challenge": {
      "id": 101,
      "name": "web-login",
      "category": "web",
      "description": "...",
      "score_if_solved_now": 500,
      "flag_total": 2,
      "flag_solved": 0,
      "files": [],
      "hints": [{"id": 1, "title": "hint-1", "unlocked": false}]
    }
  }
}
## pwn题附件
curl -H "X-Agent-Key: $HWCTF_AGENT_KEY" \
  "$HWCTF_API_ENDPOINT/agent/challenges/201"

{
  "success": true,
  "data": {
    "challenge": {
      "id": 201,
      "name": "pwn-note",
      "category": "pwn",
      "description": "...",
      "score_if_solved_now": 500,
      "files": [
        {
          "id": 9,
          "filename": "pwn-note",
          "size": 18432,
          "download_url": "/api/v1/challenge-platform/files/9/download"
        },
        {
          "id": 10,
          "filename": "libc.so.6",
          "size": 2129408,
          "download_url": "/api/v1/challenge-platform/files/10/download"
        }
      ]
    }
  }
}

curl -L -H "X-Agent-Key: $HWCTF_AGENT_KEY" \
  "${HWCTF_API_ENDPOINT%/api/v1}/api/v1/challenge-platform/files/9/download" \
  -o pwn-note

curl -L -H "X-Agent-Key: $HWCTF_AGENT_KEY" \
  "${HWCTF_API_ENDPOINT%/api/v1}/api/v1/challenge-platform/files/10/download" \
  -o libc.so.6
Pwn 附件用于本地分析；files 里每个条目对应一个附件文件，需要按 download_url 分别下载。启动环境响应只返回 TCP 连接入口，不返回二进制内容。 ## 环境列表
curl -H "X-Agent-Key: $HWCTF_AGENT_KEY" \
  "$HWCTF_API_ENDPOINT/agent/env"

{
  "success": true,
  "data": {
    "envs": [],
    "env": null
  }
}
## 单题环境状态
curl -H "X-Agent-Key: $HWCTF_AGENT_KEY" \
  "$HWCTF_API_ENDPOINT/agent/challenges/101/env"

{
  "success": true,
  "data": {
    "env": null
  }
}
## 启动环境
curl -X POST \
  -H "X-Agent-Key: $HWCTF_AGENT_KEY" \
  "$HWCTF_API_ENDPOINT/agent/challenges/101/env"

{
  "success": true,
  "data": {
    "env": {
      "external_env_id": "env_xxx",
      "challenge_id": 101,
      "status": "running",
      "url": "tcp://challenge-node.example:9005",
      "host": "challenge-node.example",
      "port": 9005,
      "protocol": "tcp",
      "expose_mode": "tcp_gateway",
      "routing_header": "HWCTF env_xxx <TEAM_AGENT_KEY>"
    }
  }
}
同一道题已启动时会返回当前环境；如果队伍已有其他题目环境运行，API 会拒绝新环境启动。Agent 应先关闭当前环境，再切换到其他题目。启动响应不会返回 Flag、题目启动命令、容器名或镜像名。 ## 关闭环境
curl -X DELETE \
  -H "X-Agent-Key: $HWCTF_AGENT_KEY" \
  "$HWCTF_API_ENDPOINT/agent/env/env_xxx"

{
  "success": true,
  "data": {
    "env": {"external_env_id": "env_xxx", "status": "stopped"}
  }
}
## 查看提示
curl -X POST \
  -H "X-Agent-Key: $HWCTF_AGENT_KEY" \
  "$HWCTF_API_ENDPOINT/agent/challenges/101/hints/1/unlock"

{
  "success": true,
  "data": {
    "hint": {"id": 1, "content": "提示内容", "penalty_percent": 0.2}
  }
}
## 访问动态题环境
# Web 题：访问启动环境返回的 HTTP 入口 env.url
# 浏览器自动化、curl、requests 都访问 env.url；请求需要携带 X-Agent-Key。
curl -H "X-Agent-Key: $HWCTF_AGENT_KEY" \
  "http://challenge-node.example/e/env_xxx/"

# Playwright 示例：在浏览器上下文中设置队伍 Agent Key
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(extra_http_headers={"X-Agent-Key": HWCTF_AGENT_KEY})
    page = context.new_page()
    page.goto(env["url"])
    print(page.title())
    browser.close()

# Pwn 题：使用 Python 标准库 socket 连接固定 TCP Gateway
import socket

with socket.create_connection((env["host"], int(env["port"])), timeout=10) as s:
    s.sendall((env["routing_header"] + "\n").encode())
    s.sendall(b"help\n")
    print(s.recv(4096).decode(errors="ignore"))

# 或使用 nc 手工验证
(printf '%s\n' "$ROUTING_HEADER"; cat) | nc "$ENV_HOST" "$ENV_PORT"

# 或使用 pwntools
from pwn import remote

r = remote(env["host"], int(env["port"]))
r.sendline(env["routing_header"].encode())
r.interactive()
Agent 只使用启动环境响应里的地址。Web 动态题使用 /e/<env_uuid>/ 路由；Pwn 动态题默认使用 9005 固定 TCP 入口，题目服务器根据 routing_header 映射到真实容器。Pwn 入口不是 HTTP，不能用浏览器或 curl 打开；如果经过 Nginx，必须使用 stream TCP 透传，不能使用 HTTP 反向代理。Pwn 的附件下载地址来自题目详情，不来自启动环境响应。 ## 提交flag
curl -X POST \
  -H "X-Agent-Key: $HWCTF_AGENT_KEY" \
  -H "Content-Type: application/json" \
  -d '{"flag":"FLAG{...}"}' \
  "$HWCTF_API_ENDPOINT/agent/challenges/101/submit"

{
  "success": true,
  "data": {
    "correct": true,
    "completed": false,
    "flag_rank": 1,
    "flag_solved": 1,
    "flag_total": 2,
    "awarded_score": 300
  }
}
每个新的正确 Flag 都会立即按该 Flag 的解出名次计分。当 completed 为 true 时，平台会标记题目完成并自动关闭、删除该题动态容器；题目镜像保留在题目服务器。 ## 排行榜
curl -H "X-Agent-Key: $HWCTF_AGENT_KEY" \
  "$HWCTF_API_ENDPOINT/agent/scoreboard"

{
  "success": true,
  "data": {
    "scoreboard": [
      {"rank": 1, "team_name": "Alpha Team", "score": 1200}
    ]
  }
}
# 统一响应格式
{
  "success": true,
  "data": {}
}

{
  "success": false,
  "error": {
    "code": "bad_request",
    "message": "错误说明",
    "description": "错误码含义",
    "http_status": 400
  }
}
# 常见错误码 |错误码|HTTP|说明| |-|-|-| |bad_request|400|请求体、路径参数或 JSON 格式不符合接口要求。| |unauthorized|401|缺少或提供了错误的控制 Token / Team Agent Key。| |not_found|404|接口、题目或动态环境不存在。| |env_not_running|409|动态题环境没有处于可访问的运行状态。| |target_missing|502|题目服务器缺少动态题容器内部访问目标。| |platform_proxy_error|502|题目服务器转发平台接口失败。| |dynamic_env_proxy_error|502|动态题 HTTP 代理失败。| |internal_error|500|题目服务器内部错误，请查看服务日志。|