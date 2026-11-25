# TestFlow 极简接口 & UI 自动化测试工作台

![Python](https://img.shields.io/badge/Python-3.10%2B-3776ab?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688?logo=fastapi&logoColor=white)
![Playwright](https://img.shields.io/badge/Playwright%20%2B%20Selenium-Dual%20Engine-2ea44f)
![License](https://img.shields.io/badge/License-MIT-blue)

**TestFlow** 是一个面向软件测试工程师的轻量级一体化自动化测试平台，将 **Postman 式接口调试 + Playwright / Selenium 双引擎 UI 自动化 + Pytest 调度引擎 + Allure 可视化报告** 整合在一个零构建、开箱即用的本地 Web 工作台中。

**无需编写或维护自动化测试代码**，通过界面配置或编辑 YAML 文件，即可完成“接口造数 → 浏览器校验”全流程自动化测试。

---

## 核心特性

1. **类 Postman 接口调试（支持 cURL / Postman / Swagger 导入与历史记录）**
   - 支持 `GET / POST / PUT / DELETE / PATCH`、Headers、Query Params，以及 **JSON / x-www-form-urlencoded / form-data（含文件上传） / Raw** 多种 Body 类型。
   - 支持 `{{变量名}}` 与内置动态函数（`{{$timestamp}}`、`{{$uuid}}`、`{{$random_int(1,100)}}`、`{{$random_str(8)}}` 等），支持一键解析 `cURL`、查看最近 20 条 **调试历史**、批量导入 **Postman Collection v2.1 / Swagger (OpenAPI) JSON**。
   - 响应区域支持 **响应体 / 响应头** 切换查看与一键复制，调试通过的接口可一键 **“保存为用例步骤”**。

2. **API + UI 零代码混合编排**
   - 同一条用例中自由组合 **接口步骤 (API)** 与 **浏览器步骤 (UI)**，共用同一套变量上下文与登录 Cookie（自动保持 Session），支持步骤级 **启用/跳过**、**复制**、**折叠/展开**、**单步 `▶ 试跑`** 与 **直接从 cURL 添加步骤**。
   - **步骤内嵌运行结果**：运行后直接在当前步骤卡片内查看实际请求、格式化响应、提取变量、断言对比表与 UI 截图，无需来回切页排查；支持执行中途一键 **停止运行**。
   - **API 步骤**：支持 JSON / 表单 / 文件上传（自动识别 MIME 类型），支持 JSONPath / 响应头 (`header:`) / 正则 (`regex:`) 变量提取与 **11 种内置断言**。
   - **UI 步骤**：支持 **31 种常用浏览器动作** 与 **6 种定位策略**（CSS、XPath、ID、Name、文本包含、Placeholder）。

3. **Playwright / Selenium 双引擎 + 多浏览器自由切换**
   - 顶部栏一键切换 **UI 引擎（Selenium / Playwright）** 与 **浏览器（自动 / Chrome / Edge / Firefox）**。
   - **Selenium 模式**：支持 Chrome（内置国内镜像自动匹配对应版本 ChromeDriver）、Edge、Firefox。
   - **Playwright 模式**：支持 Chrome / Edge / Firefox 通道与自动回退，自带智能等待。
   - 无论哪种引擎，UI 步骤异常时均**自动截取全屏 PNG 并挂载到 Allure 报告**。

4. **Pytest + Allure + 内置免环境 HTML 双报告**
   - 后台异步调用 Pytest 执行选中的单条或批量用例，支持 `Ctrl+S` 快捷保存与未保存防丢提醒。
   - 每次运行自动生成 **内置单文件中文 HTML 报告**（零外部依赖，未安装 Java / Allure CLI 也可直接查看完整入参出参与失败截图），若本机已安装 Allure 则同时生成中文 Allure 报告并支持一键切换。

5. **统一撤销/重做与桌面级快捷键**
   - 用例编排与环境变量均内置 50 步快照历史栈，顶部 **`↶` / `↷`** 按钮与 **`Ctrl+Z` / `Ctrl+Y` / `Ctrl+Shift+Z`** 快捷键完全同步（自动保留 JSON 草稿修改）。
   - 支持 `Ctrl+S`（保存）、`Ctrl+Enter`（发送调试请求 / 运行当前用例）、`Ctrl+F`（搜索用例）、`Ctrl+N`（新建用例）、`Ctrl+1~4`（切页）、`F1`（快捷键一览）、`Esc`（关闭弹窗）。

6. **Git 友好 & 开箱即用演示靶场**
   - 所有用例以标准 YAML 存储在 `cases/` 目录，环境配置存储在 `config/envs.yaml`，天然支持 Git 版本管理与团队协作。
   - 内置离线演示靶场（`/demo/page` 与 `/demo/api/*`）及 2 条示例用例，首次启动即可体验完整闭环。

---

## 系统架构

```text
[ 浏览器 Web UI (static/) ]  ← 接口调试 / 零代码用例编排 / 环境管理 / 在线看报告
            ↓
[ FastAPI 后端 (server/main.py) ]  ← 用例 CRUD / 单步调试 / 异步调度 Pytest & Allure
            ↓
[ Pytest 执行引擎 (engine/test_runner.py) ]
   ├── API 执行器 (engine/api_runner.py)      ← requests + JSONPath 提取 + 断言 + Allure 附件
   └── UI 双引擎 (engine/ui_runner.py)        ← Selenium / Playwright 统一步骤协议 + 失败截图
            ↓
[ Allure HTML 报告 (reports/allure-report/) ]
```

---

## 快速开始

### 方式一：直接双击桌面版 `.exe` 启动（最推荐）
如果你已经打包好了程序，直接双击运行：
```text
dist\TestFlow\TestFlow.exe
```
程序会直接弹出独立的桌面应用窗口（无需手动打开浏览器），用例、配置和报告会自动保存在 `TestFlow.exe` 同级目录的 `cases/`、`config/`、`reports/` 中。

### 方式二：从源码运行或自行打包 `.exe`

#### 1. 环境要求
- Python 3.10+
- 本地已安装 Google Chrome 或 Microsoft Edge
- 已安装 [Allure CLI](https://allurereport.org/docs/install/) 并配置到系统 `PATH`（用于生成 HTML 报告）

#### 2. 安装依赖并启动

```powershell
pip install -r requirements.txt
# 弹出独立桌面窗口运行（默认）
python app.py

# 或者仅以本地网页服务模式运行（浏览器访问 http://127.0.0.1:8000）
python app.py --web
```

#### 3. 打包成 Windows `.exe` 桌面程序

```powershell
python build_exe.py

# 如需同时生成不含个人用例/驱动的干净 GitHub Release 发布包：
python build_exe.py --release-zip
```
打包完成后会在 `dist\TestFlow\TestFlow.exe` 生成可直接双击运行的桌面程序（加上 `--release-zip` 时会额外生成 `dist\TestFlow-Windows-x64.zip`）。

> 详细操作步骤请参阅：[📘 TestFlow 详细使用说明书 (MANUAL.md)](./MANUAL.md)

---

## 命令行（CI/CD）运行方式

除了 Web 界面点击运行，也可以直接在命令行通过 Pytest 运行（方便接入 Jenkins / GitLab CI / GitHub Actions）：

```powershell
# 设置环境变量并运行全部用例（Windows PowerShell）
$env:TESTFLOW_ENV="local_demo"
$env:TESTFLOW_UI_ENGINE="playwright"   # 可选 selenium 或 playwright
$env:TESTFLOW_HEADLESS="1"             # 1=无头模式，0=有头模式
pytest engine/test_runner.py -v --alluredir=reports/allure-results

# 生成并查看 Allure 报告
allure generate reports/allure-results -o reports/allure-report --lang zh --clean
allure open reports/allure-report
```

---

## 目录结构

```text
testflow/
├── app.py                     # 桌面版 & Web 服务一键启动入口
├── build_exe.py               # PyInstaller 打包脚本（支持 --release-zip）
├── requirements.txt           # Python 依赖清单
├── pytest.ini                 # Pytest 配置
├── LICENSE                    # MIT 开源协议
├── MANUAL.md                  # 详细功能使用说明书
├── config/
│   └── envs.yaml              # 多环境变量配置
├── cases/
│   ├── 01_demo_api.yaml       # 示例 1：纯接口自动化用例
│   └── 02_demo_hybrid.yaml    # 示例 2：API + UI 混合自动化用例
├── engine/
│   ├── context.py             # 变量池、{{var}} 模板渲染与 JSONPath 提取
│   ├── api_runner.py          # 接口请求执行器与断言引擎
│   ├── ui_runner.py           # Selenium & Playwright 双引擎执行器
│   ├── html_report.py         # 零依赖内置轻量 HTML 报告生成器
│   ├── paths.py               # 源码与打包模式统一路径解析
│   ├── win_chrome.py          # Windows 原生 DWM 无边框窗口与缩放支持
│   └── test_runner.py         # Pytest 用例调度入口
├── server/
│   ├── main.py                # FastAPI 服务与异步执行接口
│   └── demo_app.py            # 内置演示靶场（登录/订单 API + 订单中心网页）
├── static/                    # 零构建原生前端界面
├── drivers/                   # 自动下载的 ChromeDriver 缓存（Git 忽略）
├── reports/                   # Allure 原始结果与 HTML 报告（Git 忽略）
└── .github/workflows/test.yml # GitHub Actions 自动测试工作流
```

---

## 上传 GitHub 注意事项

1. `.gitignore` 已默认忽略 `reports/`、`drivers/`、`__pycache__/`、`*.pyc` 与 `.env`。
2. 推送到公开仓库前，请检查 `config/envs.yaml` 和 `cases/*.yaml`，确保不包含公司真实域名、内网地址、真实账号密码或 Token。
3. 仓库已内置 `.github/workflows/test.yml`，推送代码后可在 GitHub Actions 中自动运行验证。
