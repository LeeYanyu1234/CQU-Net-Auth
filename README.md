# CQU-Net-Auth

重庆大学校园网自动认证脚本（Python 版本）。

本项目会循环检测网络连通性，并在掉线、未认证或认证账号不符合预期时，调用重庆大学校园网门户接口完成重新认证。脚本仅依赖 Python 标准库，适合放在 Windows 批处理、Linux systemd 服务或其他守护进程中长期运行。



## 1 功能概览

- 自动查询当前校园网门户认证状态。
- 支持 `pc` 和 `mobile` 两种终端类型登录。
- 启动时会尝试先注销已有会话，再按配置账号重新登录。
- 循环检测网络连通性，默认使用 socket 探测，也可切换为 HTTP HEAD 探测。
- 检测到已登录账号不是配置账号时，会尝试先下线旧账号。
- 支持 Linux 下按网卡名绑定出口接口；Windows 下不支持 `--interface`。
- 可选记录最近 10 条本机 IP / 门户 IP 历史。
- 可选通过 QQ 邮箱 SMTP 发送门户 IP 变化通知，并支持发送冷却时间。
- 支持命令行参数和环境变量两种配置方式。



## 2 项目结构

```text
CQU-Net-Auth/
├─ cqu_net_auth/
│  ├─ app.py
│  ├─ cli.py
│  ├─ config.py
│  ├─ exceptions.py
│  ├─ logging_setup.py
│  ├─ core/
│  │  └─ loop.py
│  ├─ net/
│  │  ├─ connectivity.py
│  │  └─ opener.py
│  ├─ notify/
│  │  ├─ mailer.py
│  │  └─ service.py
│  ├─ portal/
│  │  └─ client.py
│  └─ storage/
│     └─ ip_history.py
├─ module_tests/
│  ├─ check_status.py
│  ├─ login_campus.py
│  ├─ logout_campus.py
│  └─ send_mail.py
├─ logs/
├─ login.py
├─ 登录校园网脚本.bat
├─ LockScreen.bat
├─ LICENSE
└─ README.md
```



## 3 各文件作用

- `login.py`：项目入口，调用 `cqu_net_auth.app:main`。
- `cqu_net_auth/app.py`：关闭系统代理影响，注册退出信号，解析配置并启动主循环。
- `cqu_net_auth/cli.py`：命令行参数、环境变量读取和配置校验。
- `cqu_net_auth/config.py`：运行配置数据结构。
- `cqu_net_auth/logging_setup.py`：日志级别和输出格式配置。
- `cqu_net_auth/exceptions.py`：项目自定义异常。
- `cqu_net_auth/core/loop.py`：核心认证循环，负责检测、注销、登录、记录 IP 和触发通知。
- `cqu_net_auth/net/connectivity.py`：socket / HTTP 网络连通性探测。
- `cqu_net_auth/net/opener.py`：构建 `urllib` opener，支持禁用代理和 Linux 网卡绑定。
- `cqu_net_auth/portal/client.py`：校园网门户状态查询、登录、解绑和注销接口封装。
- `cqu_net_auth/notify/mailer.py`：通过 QQ 邮箱 SMTP over SSL 发送邮件。
- `cqu_net_auth/notify/service.py`：IP 变化通知和冷却时间控制。
- `cqu_net_auth/storage/ip_history.py`：IP 历史文件读写，以及代理环境变量模板生成。
- `登录校园网脚本.bat`：Windows 批处理启动示例，会将日志写入 `logs/`。
- `LockScreen.bat`：Windows 锁屏命令。
- `module_tests/`：手动模块验证脚本，用于真实查询、登录、注销和发信测试。



## 4 运行要求

- Python 3.10+。
- 无第三方 Python 包依赖，运行主程序只需要标准库。
- 需要处于重庆大学校园网环境，且能访问 `login.cqu.edu.cn`。
- 如启用邮件通知，需要 QQ 邮箱开启 SMTP 服务，并使用邮箱授权码而不是邮箱登录密码。
- 如在 Linux 使用 `--interface` 绑定网卡，运行环境需要支持 `SO_BINDTODEVICE`。



## 5 快速开始

### 5.1 Windows 脚本示例

可以直接编辑 `登录校园网脚本.bat` 中的参数，然后双击运行；日志会追加到 `logs/run-YYYYMMDD.log`。

建议将真实账号、密码、邮箱授权码替换为自己的值，并避免提交到 Git：

```bat
@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "LOG_DIR=%SCRIPT_DIR%logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd"') do set "LOG_DATE=%%i"
set "LOG_FILE=%LOG_DIR%\run-%LOG_DATE%.log"

echo [%date% %time%] Network login start >> "%LOG_FILE%"
python "%SCRIPT_DIR%login.py" ^
  --log_level debug ^
  --account 你的校园网账号 ^
  --password 你的校园网密码 ^
  --term_type pc ^
  --interval 180 ^
  --check_with_http ^
  --http_url https://www.baidu.com ^
  --file_path "D:\path\to\Desktop IP.txt" ^
  --mail_enable ^
  --mail_sender your@qq.com ^
  --mail_auth_code your_smtp_auth_code ^
  --mail_to "receiver@example.com" ^
  --mail_cooldown 300 >> "%LOG_FILE%" 2>&1
echo [%date% %time%] Network login end, exit_code=%errorlevel% >> "%LOG_FILE%"
```

如果不需要邮件通知，可以删除 `--mail_enable`、`--mail_sender`、`--mail_auth_code`、`--mail_to`、`--mail_cooldown` 这些参数。



### 5.2 Linux 脚本示例（systemd）

下面以仓库路径 `/home/lhx/Workspace/CQU-Net-Auth`、用户 `lhx` 为例。

#### 1. 创建启动脚本

仓库当前未包含 `start_cqu_net_auth.sh`，可以按需创建：

```bash
cd /home/lhx/Workspace/CQU-Net-Auth

cat > start_cqu_net_auth.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

cd /home/lhx/Workspace/CQU-Net-Auth
exec python3 login.py \
  --log_level info \
  --account "你的校园网账号" \
  --password "你的校园网密码" \
  --term_type pc \
  --interval 180 \
  --check_with_http \
  --http_url "https://www.baidu.com" \
  --file_path "/home/lhx/cqu_net_auth_ip.txt"
EOF

chmod +x start_cqu_net_auth.sh
```

如需绑定 Linux 网卡，可额外加入 `--interface eth0`，并将 `eth0` 替换为实际网卡名。

#### 2. 创建服务文件

```bash
sudo tee /etc/systemd/system/cqu-net-auth.service >/dev/null <<'EOF'
[Unit]
Description=CQU Net Auth Auto Login
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=lhx
WorkingDirectory=/home/lhx/Workspace/CQU-Net-Auth
ExecStart=/home/lhx/Workspace/CQU-Net-Auth/start_cqu_net_auth.sh
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

#### 3. 启用并立即启动

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now cqu-net-auth.service
```

#### 4. 查看服务状态

```bash
systemctl status cqu-net-auth.service
```

#### 5. 查看实时日志

```bash
journalctl -u cqu-net-auth.service -f
```

#### 6. 常用运维命令

```bash
sudo systemctl restart cqu-net-auth.service
sudo systemctl stop cqu-net-auth.service
sudo systemctl disable cqu-net-auth.service
```

## 6 参数说明

| 命令行参数 | 环境变量 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--account` | `ACCOUNT` | 空 | 校园网账号，必填。 |
| `--password` | `PASSWORD` | 空 | 校园网密码，必填。 |
| `--term_type` | `TERM_TYPE` | `pc` | 终端类型，只能是 `pc` 或 `mobile`。 |
| `--log_level` | `LOG_LEVEL` | `info` | 日志级别，只能是 `info` 或 `debug`。 |
| `--interval` | `INTERVAL` | `5` | 主循环检测间隔，单位秒。 |
| `--check_with_http` | `CHECK_WITH_HTTP` | `False` | 使用 HTTP HEAD 检测网络；未启用时使用 socket 检测。 |
| `--http_url` | `HTTP_URL` | `https://www.baidu.com` | HTTP 检测目标 URL。 |
| `--interface` | `INTERFACE` | 空 | Linux 网卡名；Windows 下配置该项会直接退出。 |
| `--file_path` | `FILE_PATH` | 空 | IP 历史记录文件路径；为空时不记录。 |
| `--mail_enable` | `MAIL_ENABLE` | `False` | 开启邮件通知。 |
| `--mail_sender` | `MAIL_SENDER` | 空 | 发件 QQ 邮箱。 |
| `--mail_auth_code` | `MAIL_AUTH_CODE` | 空 | QQ 邮箱 SMTP 授权码。 |
| `--mail_to` | `MAIL_TO` | 空 | 收件邮箱，多个地址可用英文逗号或分号分隔。 |
| `--mail_cooldown` | `MAIL_COOLDOWN` | `300` | 邮件通知冷却时间，单位秒。 |

命令行参数优先于环境变量。布尔环境变量可使用 `true`、`yes`、`1`、`t`、`y` 表示开启。



## 7 模块测试

`module_tests/` 下的脚本会读取 Windows 批处理文件中的配置，并对真实校园网或邮件服务发起请求：

```powershell
python module_tests\check_status.py
python module_tests\login_campus.py
python module_tests\logout_campus.py
python module_tests\send_mail.py
```

这些脚本不是单元测试，而是手动联调工具。执行前请确认当前网络环境、账号密码和邮箱配置正确。



## 8 日志与状态文件

程序日志输出格式为：

```text
2026-04-26 14:00:00,000 - INFO - main.loop_start: interval=180s
```

配置 `--file_path` 后，程序会保留最近 10 条 IP 记录，格式类似：

```text
2026-04-26 14:00:00    uid=2025xxxx    local_ip=10.x.x.x    portal_ip=10.x.x.x
```

邮件通知正文中还会附带一个以新门户 IP 生成的代理环境变量模板，便于在其他机器上快速更新代理配置。



## 9 注意事项

- 请勿将真实账号、密码、邮箱授权码提交到公开仓库。
- 门户返回“账号不存在”或“密码错误”时，程序会退出。
- 门户返回需要等待 5 分钟的提示时，程序会暂停 300 秒后继续。
- Windows 下不要配置 `--interface`；该功能仅面向 Linux。
- 使用 `--file_path` 时，请确认运行用户对目标目录有写权限。
- 如果 systemd 服务不断重启，优先用 `journalctl -u cqu-net-auth.service -f` 查看账号、网络和权限错误。



## 10 许可证

MIT License.
