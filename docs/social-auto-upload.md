# 视频生成后自动发布到社交平台

MoneyPrinterTurbo-NAS 现在可以在视频生成完成后复用原有异步发布队列，并通过 [dreammis/social-auto-upload](https://github.com/dreammis/social-auto-upload) 的 `sau` CLI 自动发布到国内社交平台。WebUI 顶部新增了 **“社交平台发布”** 功能页，可以直接配置自动发布、平台账号、Upload-Post，并查看账号与最近发布状态。

这套集成不会替换原有 Upload-Post：

- TikTok / Instagram / YouTube 仍可继续使用 Upload-Post API。
- 抖音 / 小红书 / 快手 / Bilibili 使用 social-auto-upload 的浏览器自动化。
- 视频号（`tencent`）代码入口已接入适配器，建议先通过 WebUI 的账号检查或 CLI 验证登录态后再开启自动发布。
- 两种 provider 可以同时开启，任务状态统一写入现有 `cross_post_state` / `cross_post_results`。
- 上传失败不会把已经成功生成的视频任务改成失败；只会把发布状态标记为失败并保存错误信息。

## 1. 重新构建 Docker 镜像

Dockerfile 会固定安装 social-auto-upload 的一个已验证提交，并安装 patchright Chromium。首次构建会比以前更大、耗时更长，这是浏览器自动化运行时带来的正常开销。

```bash
git pull
docker compose down
docker compose up -d --build
```

> **NAS fork 请使用仓库中的 `docker-compose.yml` 本地构建。** `docker-compose.release.yml` 仍指向 MoneyPrinterTurbo 上游预构建镜像，不包含本 fork 新增的 social-auto-upload 运行时和“社交平台发布”页面。

当前默认固定的上游提交可以通过 Docker build args 覆盖：

```text
SOCIAL_AUTO_UPLOAD_REPO
SOCIAL_AUTO_UPLOAD_REF
```

除非已经验证过新版选择器和登录流程，否则建议保持仓库默认 pin，不要自动跟随 social-auto-upload 的 main。

## 2. 从 WebUI 配置自动发布

打开 MoneyPrinterTurbo 后，顶部会显示两个一级功能入口：

```text
视频生成    社交平台发布
```

进入 **社交平台发布** 后，可以直接完成：

- **国内平台**：启用浏览器发布、选择抖音/小红书/快手/Bilibili/视频号、配置平台账号别名、标签、默认说明和高级参数。
- **海外平台**：配置 Upload-Post 用户名/API Key，选择 TikTok/Instagram/YouTube Shorts，并设置 YouTube 可见性。
- **账号与运行状态**：检查 `sau` CLI、Chromium、工作目录、Cookie 目录是否就绪，并对各个平台执行只读的 Cookie 登录检查。
- **最近自动发布状态**：查看等待发布、发布中、成功、失败数量，以及最近任务的平台和错误；页面会自动刷新状态。

WebUI 修改的发布设置会被保存到 `config.toml`。发布服务现在会在新任务开始发布前重新读取配置，因此正常情况下修改平台、账号或自动发布开关后**不需要重启容器**；如果当时有视频任务正在占用配置，设置会在该任务释放配置后自动保存，并对后续任务生效。

## 3. 准备平台登录态

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

在 **社交平台发布 → 账号与运行状态** 中，每个平台都会显示对应的登录命令。首次登录例如：

```bash
docker exec -it moneyprinterturbo-webui sau douyin login --account creator --headless
docker exec -it moneyprinterturbo-webui sau kuaishou login --account creator --headless
docker exec -it moneyprinterturbo-webui sau xiaohongshu login --account creator --headless
docker exec -it moneyprinterturbo-webui sau bilibili login --account creator
```

登录后既可以在 WebUI 点 **“检查登录”**，也可以直接用 CLI：

```bash
docker exec -it moneyprinterturbo-webui sau douyin check --account creator
docker exec -it moneyprinterturbo-webui sau kuaishou check --account creator
docker exec -it moneyprinterturbo-webui sau xiaohongshu check --account creator
docker exec -it moneyprinterturbo-webui sau bilibili check --account creator
```

“检查登录”只验证 Cookie 是否有效，不会上传任何内容。

如果 NAS 的无头登录或二维码操作不方便，也可以在另一台电脑按 social-auto-upload 官方方式完成登录，然后把生成的 `cookies/*.json` 复制到宿主机的 `storage/social-auto-upload/cookies/`。重建容器后这些登录态仍会保留。

## 4. 手工配置 config.toml（可选）

正常情况下现在可以直接使用 WebUI，不需要手工编辑。若需要无人值守部署或批量配置，把下面这些键加入现有 `config.toml` 的 **已有 `[app]` 段内**，不要再创建第二个 `[app]`：

```toml
social_auto_upload_enabled = true
social_auto_upload_auto_upload = true
social_auto_upload_platforms = ["douyin", "xiaohongshu"]
social_auto_upload_accounts = { douyin = "creator", xiaohongshu = "creator" }
social_auto_upload_default_account = ""
social_auto_upload_tags = ["AI", "科普"]
social_auto_upload_description = ""
social_auto_upload_bilibili_tid = 249
social_auto_upload_headless = true
social_auto_upload_timeout = 900
social_auto_upload_command = "sau"
social_auto_upload_workdir = "/opt/social-auto-upload"
```

Upload-Post 可以同时开启：

```toml
upload_post_enabled = true
upload_post_api_key = "..."
upload_post_username = "..."
upload_post_platforms = ["tiktok", "instagram", "youtube"]
upload_post_auto_upload = true
```

视频生成完成后，两组平台会进入同一个 MoneyPrinterTurbo 发布任务。Upload-Post 仍按一次 API 请求处理其平台；social-auto-upload 会逐个平台执行 `sau <platform> upload-video`，这样某一个国内平台失败时可以明确看到是哪一个平台和哪个账号出错。

## 5. 发布状态和错误排查

MoneyPrinterTurbo 使用以下任务字段：

```text
cross_post_state
cross_post_results
cross_post_error
```

social-auto-upload 的结果还会附带：

```text
provider = "social-auto-upload"
platform
account
returncode
message / error
```

这些状态会直接显示在 **社交平台发布 → 最近自动发布状态** 中。常见失败原因：

1. `social-auto-upload CLI not found`：当前镜像没有重新构建，或者实际运行的是上游/旧 GHCR 镜像。
2. `no account configured`：对应平台没有填写账号别名，也没有设置默认账号。
3. `cookie is missing or expired`：在“账号与运行状态”中检查失败，需要重新登录该平台或更新宿主机持久化 Cookie。
4. Chromium/页面元素错误：平台页面结构发生变化。先在容器中手工运行同一条 `sau ... upload-video` 验证；如果上游已经修复，再更新 Dockerfile 的 `SOCIAL_AUTO_UPLOAD_REF`。
5. 抖音触发短信二次验证：这是上游平台登录/风控流程，不属于视频生成失败。建议先在 social-auto-upload 环境里完成账号验证后再开启全自动发布。

## 6. 当前设计边界

为了不把平台选择器、反自动化细节和频繁变化的登录代码复制进 MoneyPrinterTurbo，本项目只维护一层稳定 adapter，真正的平台操作仍由 social-auto-upload 负责。这样以后平台页面变化时通常只需要升级被 pin 的上游版本，而不需要改视频生成主流程。

目前国内平台自动发布使用视频主题作为标题；如果未配置 `social_auto_upload_description`，描述默认也使用视频主题。后续如果需要，可以再把 MoneyPrinterTurbo 的脚本文案和 LLM 社媒元数据生成结果按平台传给该 adapter。
