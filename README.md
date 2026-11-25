# 约饭 · YUEFAN

**让每一次聚餐，都不再纠结。**

基于真实地理位置、消费预算与多人投票的聚餐决策工具。发起人创建房间，朋友通过邀请链接加入，无需安装 App。

[English](README.en.md) · [架构与算法](docs/ARCHITECTURE.md) · [隐私与安全](SECURITY.md)

![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB) ![Platform](https://img.shields.io/badge/Platform-Mobile%20Web-0071E3) ![Version](https://img.shields.io/badge/Version-1.0.0--rc.1-555555)

## 为什么做约饭？

多人聚餐时，餐厅选择经常需要重复沟通：距离是否公平？价格是否合适？谁还没投票？约饭把这些问题整合到同一个共享房间中，让参与者共同决定，而不是由一个人替所有人选择。

## 功能

- 2–12 人共享房间，朋友免注册加入，浏览器自动请求定位；全员定位成功才开始选餐厅。
- 高德真实餐厅搜索，默认 20 km，按人均预算、评分和公平距离推荐。
- 实时成员状态、一人一票、房主提前结束、按票数排序并显示选择人；同票按名称 A–Z（中文拼音）。
- Apple 风格界面，浅色 / 深色 / 跟随系统，字体与减少动态效果设置，中英文界面。
- 支持 iOS、Android 与桌面浏览器，无需第三方 Python 依赖。

## 快速开始

需要 Python 3.9+ 与自己的高德地图 Web 服务 Key。不要将 Key 上传至 GitHub。

1. 下载或克隆仓库，终端进入项目根目录（含 `server.py`）。
2. 运行 `python3 setup_amap.py`，输入高德 Key；脚本会实际查询餐厅并验证后保存至 `.amap_key`。
3. 运行 `python3 server.py`，在本机访问 <http://127.0.0.1:8000>。

Windows 若未配置 `python3` 命令，请用 `py -3` 或 `python`。也可以通过环境变量 `AMAP_KEY` 配置密钥；可选腾讯地图配置见 `setup_tencent.py`。环境变量由运行环境注入，程序不会自动读取 `.env`。

没有有效地图配置时不能创建真实房间。地图调用失败时不会退回模拟餐厅。演示数据仅供显式启用的开发测试使用，默认禁用。

### 手机联机测试

手机浏览器定位需要 HTTPS。可使用 Cloudflare 临时隧道进行小范围、受控的测试（[官方说明](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/)）。安装 cloudflared 后，在另一个终端执行：

```sh
cloudflared tunnel --protocol http2 --url http://127.0.0.1:8000
```

如果安装在 `~/.local/bin`，可用 `~/.local/bin/cloudflared` 替换命令；Mac 也可运行 `bash share.command`。双方从同一个实际生成的 HTTPS 网址进入。房主登录、定位、设置人数和预算，复制房间邀请链接；朋友打开并授权定位；全员定位后开始选餐厅；提交投票后查看结果。

临时网址可能变化，两端终端需要持续运行。临时隧道不是正式部署方案，也不保证所有网络环境可访问。请勿将 localhost 或 127.0.0.1 作为好友邀请地址。不要使用真实账号密码，不要公开传播测试隧道。

## 推荐规则

公平距离代价 = 0.7 × 平均直线距离 + 0.3 × 最远直线距离。综合推荐评分与距离分别占约 95.66% 和 4.34%；人气和销量因缺乏可靠授权数据而不计入。人均预算 ±20% 优先，营业状态优先，独立价格排序不受预算分组限制。最后投票结果仅按票数降序、名称 A–Z 排序。详见[算法说明](docs/ARCHITECTURE.md)。

## 测试

```sh
python3 -m unittest -v
node --check public/app.js
node test_results_ui.cjs
node test_theme.cjs
node test_roster18.cjs
node test_location_ui19.cjs
```

发布候选包在 Python 3.13 / Node 22 环境中通过 38 项 Python 自动化测试及以上前端检查；Python 3.9 是源码目标兼容版本，未在此次环境中重新测试。地图接口在自动化测试中使用替身，不代表真实 API 可用性。此次浏览器自动化导航被环境策略阻止，未生成可核实的新截图，欢迎通过真机测试反馈。

## 隐私与使用限制

服务器将账户、房间与参与者位置存入本地 SQLite 数据库；位置用于地图服务请求与距离计算。成员不会直接获得其他人的精确坐标，但距离信息可能推断大致位置。请在知情同意后使用。当前版本属于个人项目/受控试用，尚不具备生产级限流、位置自动清除和账号注销等功能。详见 [SECURITY.md](SECURITY.md)。

地图数据、照片和团购链接不属于本项目的开源授权范围，须遵守各数据提供方条款。项目不内置大众点评、美团或抖音商业数据集，不虚构销量或热度。

## 项目与许可

由项目发起人提出产品设计、需求与规则，使用 AI 辅助实现和迭代。第三方拼音映射声明见 [PINYIN-NOTICE.txt](PINYIN-NOTICE.txt)。本包为 v1.0.0 发布候选，项目许可证尚待权利人确认；在正式添加 LICENSE 前，不授予额外的源码再分发许可。建议先使用私有仓库。
