# 五子棋对战

架构：

- 后端：Django + Django REST Framework + Channels
- 前端：Vue 3 + Vite
- 本地数据库：SQLite
- 生产推荐：Render 部署 Django/PostgreSQL，Netlify 部署 Vue

已实现：游客单机、账号注册/登录、联机房间、密码房间、WebSocket 同步、房间聊天、离开房间自动清理空房、单机 AI、胜负判定、黑棋禁手规则（长连、双四、双三）、全局音频设置。

## 本地运行

后端：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python manage.py migrate
.\.venv\Scripts\python manage.py runserver 0.0.0.0:8000
```

前端：

```powershell
cd frontend
npm.cmd install --registry=https://registry.npmjs.org --cache ..\.npm-cache
npm.cmd run dev
```

打开 `http://localhost:5173`。

## 部署

详细步骤见 [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)。Render Blueprint 配置在仓库根目录的 `render.yaml`，Netlify 前端配置在仓库根目录的 `netlify.toml`。
