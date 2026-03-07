# SMSBoom - 短信压力测试工具 (重构版)

原作者仓库 SMSBoom 在网上被疯传、各种魔改，版本泛滥——但，**绝大多数都是垃圾**。

## ✨ 为什么选择本项目

网络上流传的仓库，接口早已大面积失效且无维护、代码逻辑混乱、界面错误，基本无法使用，本项目在这些混乱的版本基础上进行了深度的**改造、修复与接口洗牌**。**不是简单的fork，是重做。**

- **原接口99%已失效** → 全部剔除无效接口，**亲自纯手工收集，逐一抓包、测试并录入新接口**，真实有效，存活率极高。
- **全功能 Web 后台**：基于 Flask 的可视化管理界面，支持：
  - **实时测试**：一键测试单个或批量接口，自动判定有效性。
  - **批量管理**：支持接口批量测试、批量删除、条件筛选、存活状态标记、导入/导出 JSON。
  - **多 UI 风格**：内置多种界面风格。
  - **交互优化**：支持列显示控制、拖拽排序、手机号历史记录、停止测试等实用功能。
- **新增采集中心** → 支持从多个采集源抓取接口，省去手动查找
- **新增 Playwright 抓包模式** → 启动真实浏览器，手动触发验证码，自动捕获含手机号的 API 请求并导入。
- **修复原版各种Bug** → 界面错误、代码逻辑问题等

## 📖 快速开始

### 环境要求
- Python 3.8+

### 安装与环境配置

推荐使用虚拟环境以保持系统纯净。

**方案一：使用 `pipenv` (推荐)**
```shell
# 安装 pipenv
pip install pipenv
# 安装依赖
pipenv install       # 仅核心功能
pipenv install --dev # 使用 Web 管理后台
# 进入虚拟环境
pipenv shell
```

**方案二：使用原生 `venv`**
```shell
python -m venv venv

# Windows
.\venv\Scripts\activate
# Linux/macOS
source venv/bin/activate
# 安装依赖
pip install -r requirements.txt      # 仅核心功能
pip install -r requirements-dev.txt  # Web 管理后台
```

### 运行方式

#### 1. Web 可视化模式
```shell
# 启动 Flask 后台 (默认监听 9090 端口)
python run_flask_app.py start -p 9090
```
访问 `http://127.0.0.1:9090/admin/` 即可进入管理后台。

#### 2. 命令行模式
默认使用 `api.json` 中的接口进行测试。
```shell
# 启动 64 线程，对目标手机号进行 1 轮测试
python smsboom.py run -t 64 -p 188xxxxxxxx
# 启动 64 线程，循环测试 60 次，间隔 30 秒
python smsboom.py run -t 64 -p 188xxxxxxxx -f 60 -i 30
# 使用指定的接口 json 文件
python smsboom.py run -p 188xxxxxxxx -a custom_api.json
```

## ⚖️ 免责声明

1. 本程序仅供开发者进行系统性能压力测试、接口安全性验证及学习研究使用。
2. 严禁用于任何形式的非法骚扰、恶意攻击或盈利活动。
3. 使用者因滥用本项目产生的一切法律后果由其自行承担，作者不承担任何连带责任。
4. 请在遵守当地法律法规的前提下使用。
