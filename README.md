# CQU-Net-Auth

重庆大学校园网自动认证脚本（Python 版本）。

本项目会循环检测网络连通性，在掉线时自动调用校园网门户接口重新认证；支持 `pc/mobile` 终端类型、可选 HTTP 探测、可选网卡绑定（Linux）、可选邮件通知，以及门户 IP 历史记录落盘。

## 功能概览

- 自动检测网络连通性（`socket` 或 `HTTP HEAD`）
- 自动登录校园网门户（`pc` / `mobile`）
- 检测到“已登录但账号不是当前账号”时尝试先下线旧账号
- 可选记录最近 10 条认证 IP 历史到文件
- 可选邮件通知门户 IP 变化（冷却时间控制）
- 支持环境变量和命令行参数两种配置方式

## 项目结构

```text
CQU-Net-Auth/
├─ .gitignore
├─ LICENSE
├─ README.md
├─ login.py
├─ LockScreen.bat
├─ 登录校园网脚本.bat
└─ cqu_net_auth/
   ├─ __init__.py
   ├─ app.py
   ├─ cli.py
   ├─ config.py
   ├─ exceptions.py
   ├─ logging_setup.py
   ├─ core/
   │  ├─ __init__.py
   │  └─ loop.py
   ├─ net/
   │  ├─ __init__.py
   │  ├─ connectivity.py
   │  └─ opener.py
   ├─ portal/
   │  ├─ __init__.py
   │  └─ client.py
   ├─ notify/
   │  ├─ __init__.py
   │  ├─ mailer.py
   │  └─ service.py
   └─ storage/
      ├─ __init__.py
      └─ ip_history.py
```

## 各文件作用

- `.gitignore`：忽略 Python 缓存、`.vscode`、本地批处理脚本。
- `LICENSE`：MIT 许可证。
- `login.py`：启动入口（转发到 `cqu_net_auth.app:main`）。
- `LockScreen.bat`：Windows 锁屏命令。
- `登录校园网脚本.bat`：Windows 示例启动脚本。
- `cqu_net_auth/app.py`：初始化信号处理、解析参数、启动主循环。
- `cqu_net_auth/cli.py`：参数定义、环境变量读取、配置校验。
- `cqu_net_auth/config.py`：`Config` 数据结构。
- `cqu_net_auth/logging_setup.py`：日志级别与格式配置。
- `cqu_net_auth/exceptions.py`：项目异常类型定义。
- `cqu_net_auth/core/loop.py`：核心状态循环（联网检测、登录、下线、通知、写文件）。
- `cqu_net_auth/net/connectivity.py`：网络探测（socket / http）。
- `cqu_net_auth/net/opener.py`：按网卡或源地址构建 `urllib` opener。
- `cqu_net_auth/portal/client.py`：校园网门户接口请求与响应解析。
- `cqu_net_auth/notify/mailer.py`：QQ 邮箱 SMTP 发信。
- `cqu_net_auth/notify/service.py`：通知逻辑与冷却时间。
- `cqu_net_auth/storage/ip_history.py`：门户 IP 历史写入与读取。

## 运行要求

- Python 3.10+
- 仅依赖 Python 标准库（无需第三方包）

## 快速开始

### 1. 命令行运行

```bash
python login.py \
  --account 2025xxxx \
  --password your_password \
  --term_type pc \
  --log_level info
```

### 2. 环境变量运行

```bash
# Windows PowerShell
$env:ACCOUNT="2025xxxx"
$env:PASSWORD="your_password"
$env:TERM_TYPE="pc"
python login.py
```

## 参数说明

| 参数 | 环境变量 | 默认值 | 说明 |
|---|---|---|---|
| `--account` | `ACCOUNT` | 空 | 校园网账号（必填） |
| `--password` | `PASSWORD` | 空 | 校园网密码（必填） |
| `--term_type` | `TERM_TYPE` | `pc` | `pc` 或 `mobile` |
| `--log_level` | `LOG_LEVEL` | `info` | `debug` 或 `info` |
| `--interval` | `INTERVAL` | `5` | 主循环间隔（秒） |
| `--check_with_http` | `CHECK_WITH_HTTP` | `False` | 是否使用 HTTP 检测网络；否则使用 socket |
| `--http_url` | `HTTP_URL` | `https://www.baidu.com` | HTTP 检测目标 URL |
| `--interface` | `INTERFACE` | 空 | Linux 网卡名（如 `eth0`）；Windows 不支持 |
| `--file_path` | `FILE_PATH` | 空 | IP 历史记录文件路径 |
| `--mail_enable` | `MAIL_ENABLE` | `False` | 是否开启邮件通知 |
| `--mail_sender` | `MAIL_SENDER` | 空 | 发件邮箱（QQ 邮箱） |
| `--mail_auth_code` | `MAIL_AUTH_CODE` | 空 | 邮箱 SMTP 授权码 |
| `--mail_to` | `MAIL_TO` | 空 | 收件邮箱 |
| `--mail_cooldown` | `MAIL_COOLDOWN` | `300` | 邮件冷却时间（秒） |

## 主流程说明

1. 读取配置并校验必要参数。
2. 进入循环，先检测网络是否连通。
3. 网络正常则等待下次检查。
4. 网络异常时读取门户认证状态。
5. 若发现已登录账号不是当前账号，尝试先下线旧账号。
6. 若未认证则执行登录；成功后记录 IP。
7. 若检测到门户 IP 变化且通知开启，则发送邮件（受 cooldown 限制）。

## 日志与状态文件

- 日志输出到标准输出，格式：`时间 - 级别 - 消息`。
- `--file_path` 指定文件时，会保存最近 10 条记录，格式示例：

```text
2026-04-05 21:00:00    uid=2025xxxx    local_ip=10.x.x.x    portal_ip=10.x.x.x
```

## 注意事项

- Windows 下传 `--interface` 会直接退出（代码显式限制）。
- 门户返回“账号不存在 / 密码错误”时程序会直接退出。
- 门户返回“等待5分钟”时程序会暂停 300 秒后继续。
- 项目包含一个本地批处理示例文件 `登录校园网脚本.bat`，建议不要提交任何明文账号、密码、邮箱授权码。

## 常见示例

### 开启 HTTP 探测

```bash
python login.py --account 2025xxxx --password your_password --check_with_http --http_url https://www.baidu.com
```

### 开启 IP 记录与邮件通知

```bash
python login.py \
  --account 2025xxxx \
  --password your_password \
  --file_path "C:\\logs\\cqu_net_auth_ip.txt" \
  --mail_enable \
  --mail_sender "your@qq.com" \
  --mail_auth_code "your_smtp_auth_code" \
  --mail_to "receiver@example.com" \
  --mail_cooldown 300
```

## 许可证

MIT License.
