# 视频生成后自动发布到国内平台

MoneyPrinterTurbo-NAS 现在可以在视频生成完成后复用原有异步发布队列，并通过 [dreammis/social-auto-upload](https://github.com/dreammis/social-auto-upload) 的 `sau` CLI 自动发布到国内社交平台。

这套集成不会替换原有 Upload-Post：

- TikTok / Instagram / YouTube 仍可继续使用 Upload-Post API。
- 抖音 / 小红书 / 快手 / Bilibili 使用 social-auto-upload 的浏览器自动化。
- 视频号（`tencent`）代码入口已接入适配器，但上游 README 仍未把它列为正式 CLI 主线，建议先测试账号后再开启自动发布。
- 两种 provider 可以同时开启，任务状态统一写入现有 `cross_post_state` / `cross_post_results`。
- 上传失败不会把已经成功生成的视频任务改成失败；只会把发布状态标记为失败并保存错误信息。

## 1. 重新构建 Docker 镜像

Dockerfile 会固定安装 social-auto-upload 的一个已验证提交，并安装 patchright Chromium。首次构建会比以前更大、耗时更长，这是浏览器自动化运行时带来的正常开销。

```bash
docker compose up -d --build
```

当前默认固定的上游提交可以通过 Docker build args 覆盖：

```text
SOCIAL_AUTO_UPLOAD_REPO
SOCIAL_AUTO_UPLOAD_REF
```

除非已经验证过新版选择器和登录流程，否则建议保持仓库默认 pin，不要自动跟随 social-auto-upload 的 main。

## 2. 准备平台登录态

容器内的 social-auto-upload 账号文件位于：

```text
/opt/social-auto-upload/cookies
```

`docker-compose.yml` 已把它持久化到宿主机：

```text
./storage/social-auto-upload/cookies
```

账号文件命名规则由上游 CLI 决定：

```text
douyin_<account>.json
kuaishou_<account>.json
xiaohongshu_<account>.json
bilibili_<account>.json
tencent_<account>.json
```

可以在 WebUI 容器中执行上游登录命令。例如：

```bash
docker exec -it moneyprinterturbo-webui sau douyin login --account creator --headless
docker exec -it moneyprinterturbo-webui sau kuaishou login --account creator --headless
docker exec -it moneyprinterturbo-webui sau xiaohongshu login --account creator --headless
docker exec -it moneyprinterturbo-webui sau bilibili login --account creator
```

登录后建议先检查 cookie：

```bash
docker exec -it moneyprinterturbo-webui sau douyin check --account creator
docker exec -it moneyprinterturbo-webui sau kuaishou check --account creator
docker exec -it moneyprinterturbo-webui sau xiaohongshu check --account creator
docker exec -it moneyprinterturbo-webui sau bilibili check --account creator
```

如果 NAS 的无头登录或二维码操作不方便，也可以在另一台电脑按 social-auto-upload 官方方式完成登录，然后把生成的 `cookies/*.json` 复制到宿主机的 `storage/social-auto-upload/cookies/`。重建容器后这些登录态仍会保留。

## 3. 配置自动发布

把下面这些键加入你现有 `config.toml` 的 **已有 `[app]` 段内**。不要再创建第二个 `[app]`。

```toml
# 启用本地浏览器自动发布
social_auto_upload_enabled = true

# 视频生成完成后自动提交发布任务
social_auto_upload_auto_upload = true

# 可选：douyin / kuaishou / xiaohongshu / bilibili / tencent
social_auto_upload_platforms = ["douyin", "xiaohongshu"]

# 每个平台对应 social-auto-upload 的 account_name。
# 如果所有平台都使用同一个别名，也可以只设置 default_account。
social_auto_upload_accounts = { douyin = "creator", xiaohongshu = "creator" }
social_auto_upload_default_account = ""

# 自动附加标签，不要写 #，程序会自动清理。
social_auto_upload_tags = ["AI", "科普"]

# 没有单独描述时默认使用视频主题；也可以设置一段固定描述。
social_auto_upload_description = ""

# Bilibili 必填分区 tid，仅在 bilibili 平台使用。
social_auto_upload_bilibili_tid = 249

# NAS 推荐保持无头模式。
social_auto_upload_headless = true

# 单个平台单条视频上传最长等待秒数。
social_auto_upload_timeout = 900

# Docker 默认值，一般无需修改。
social_auto_upload_command = "sau"
social_auto_upload_workdir = "/opt/social-auto-upload"
```

修改配置后重启 WebUI/API 进程，使发布 service 重新读取配置：

```bash
docker compose restart
```

## 4. 与 Upload-Post 同时使用

可以保留原来的配置，例如：

```toml
upload_post_enabled = true
upload_post_api_key = "..."
upload_post_username = "..."
upload_post_platforms = ["tiktok", "instagram", "youtube"]
upload_post_auto_upload = true

social_auto_upload_enabled = true
social_auto_upload_auto_upload = true
social_auto_upload_platforms = ["douyin", "xiaohongshu", "kuaishou"]
social_auto_upload_accounts = { douyin = "creator", xiaohongshu = "creator", kuaishou = "creator" }
```

视频生成完成后，两组平台会进入同一个 MoneyPrinterTurbo 发布任务。Upload-Post 仍按一次 API 请求处理其平台；social-auto-upload 会逐个平台执行 `sau <platform> upload-video`，这样某一个国内平台失败时可以明确看到是哪一个平台和哪个账号出错。

## 5. 任务结果和错误排查

MoneyPrinterTurbo 会继续使用现有字段：

```text
cross_post_state
cross_post_results
cross_post_error
```

social-auto-upload 的结果会附带：

```text
provider = "social-auto-upload"
platform
account
returncode
message / error
```

常见失败原因：

1. `social-auto-upload CLI not found`：当前镜像没有重新构建，或者使用的是旧 GHCR 镜像。
2. `no account configured`：`social_auto_upload_accounts` / `social_auto_upload_default_account` 没有对应账号。
3. `cookie is missing or expired`：重新登录该平台，或更新宿主机持久化 cookie 文件。
4. Chromium/页面元素错误：平台页面结构发生变化。先在容器中手工运行同一条 `sau ... upload-video` 验证；如果上游已经修复，再更新 Dockerfile 的 `SOCIAL_AUTO_UPLOAD_REF`。
5. 抖音触发短信二次验证：这是上游平台登录/风控流程，不属于视频生成失败。建议先在 social-auto-upload 环境里完成账号验证后再开启全自动发布。

## 6. 当前设计边界

为了不把平台选择器、反自动化细节和频繁变化的登录代码复制进 MoneyPrinterTurbo，本项目只维护一层稳定 adapter，真正的平台操作仍由 social-auto-upload 负责。这样以后平台页面变化时通常只需要升级被 pin 的上游版本，而不需要改视频生成主流程。

目前国内平台自动发布使用视频主题作为标题；如果未配置 `social_auto_upload_description`，描述默认也使用视频主题。后续如果需要，可以再把 MoneyPrinterTurbo 的脚本文案和 LLM 社媒元数据生成结果按平台传给该 adapter。
