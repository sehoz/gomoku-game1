# Django + Vue 部署步骤

推荐部署组合：

- Django 后端：Render Web Service + Render PostgreSQL
- Vue 前端：Netlify Static Site

说明：Netlify 用来部署 Vue 静态前端；Django + Channels 后端需要支持 ASGI 和 WebSocket 的服务，所以仍放在 Render。Render/Netlify 的免费额度和数据库策略可能调整；如果 Render 免费 PostgreSQL 不可用或有期限限制，保留 Render 后端不变，把 `DATABASE_URL` 换成 Neon、Supabase 或付费 PostgreSQL 的连接串即可。

## 1. 本地确认可运行

后端：

```powershell
cd backend
.\.venv\Scripts\python manage.py check
.\.venv\Scripts\python manage.py test
.\.venv\Scripts\python manage.py migrate --noinput
```

前端：

```powershell
cd frontend
npm.cmd install --registry=https://registry.npmjs.org --cache ..\.npm-cache
npm.cmd run build
```

## 2. 推送代码到 GitHub

```powershell
git init
git add .
git commit -m "Rebuild gomoku with Django and Vue"
git remote add origin https://github.com/你的用户名/你的仓库名.git
git branch -M main
git push -u origin main
```

注意：不要提交本地 `.env`、`backend/.venv`、`backend/db.sqlite3`、`frontend/node_modules`、`frontend/dist`、`.netlify`。

## 3. 部署 Django 后端到 Render

1. 打开 Render，选择 New -> Blueprint。
2. 选择 GitHub 仓库。
3. Render 会读取仓库根目录的 `render.yaml`。
4. 创建后端 Web Service 和 PostgreSQL 数据库。
5. 第一次创建时，先把环境变量填成下面这样：

```text
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=你的后端域名.onrender.com
CORS_ALLOWED_ORIGINS=http://localhost:5173
```

6. 部署成功后，打开后端健康检查地址：

```text
https://你的后端域名.onrender.com/api/health/
```

返回 `{"ok": true}` 即后端可用。

后端启动命令已经写在 `render.yaml`：

```text
daphne -b 0.0.0.0 -p $PORT gomoku_project.asgi:application
```

它支持 HTTP API 和 WebSocket。当前配置按单实例部署设计；如果以后扩容多实例，需要给后端配置 Redis/Key Value，并设置 `REDIS_URL`。

## 4. 部署 Vue 前端到 Netlify

前端部署配置已经写在仓库根目录的 `netlify.toml`：

```text
Build command: npm --prefix frontend install --registry=https://registry.npmjs.org --no-audit --no-fund && npm --prefix frontend run build
Publish directory: frontend/dist
```

### 4.1 使用 Netlify CLI 检查登录

在仓库根目录执行：

```powershell
npx.cmd --yes --package netlify-cli --registry=https://registry.npmjs.org --cache .\.npm-cache netlify status
```

如果提示未登录，执行：

```powershell
npx.cmd --yes --package netlify-cli --registry=https://registry.npmjs.org --cache .\.npm-cache netlify login
```

浏览器完成授权后，再运行一次 `netlify status` 确认已登录。

### 4.2 创建或关联 Netlify 站点

如果这是第一次部署该仓库：

```powershell
npx.cmd --yes --package netlify-cli --registry=https://registry.npmjs.org --cache .\.npm-cache netlify init
```

按提示选择你的 Netlify team，创建新站点或关联已有站点。构建设置直接采用 `netlify.toml`。

如果你已经在 Netlify 创建过站点，也可以在仓库根目录执行：

```powershell
npx.cmd --yes --package netlify-cli --registry=https://registry.npmjs.org --cache .\.npm-cache netlify link
```

### 4.3 设置 Netlify 环境变量

可以在 Netlify Dashboard 设置，也可以用 CLI 设置：

```text
VITE_API_BASE_URL=https://你的后端域名.onrender.com/api
VITE_WS_BASE_URL=wss://你的后端域名.onrender.com/ws
```

CLI 示例：

```powershell
npx.cmd --yes --package netlify-cli --registry=https://registry.npmjs.org --cache .\.npm-cache netlify env:set VITE_API_BASE_URL https://你的后端域名.onrender.com/api
npx.cmd --yes --package netlify-cli --registry=https://registry.npmjs.org --cache .\.npm-cache netlify env:set VITE_WS_BASE_URL wss://你的后端域名.onrender.com/ws
```

### 4.4 先发预览部署

```powershell
npx.cmd --yes --package netlify-cli --registry=https://registry.npmjs.org --cache .\.npm-cache netlify deploy --build
```

确认预览地址可用后，再发布生产：

```powershell
npx.cmd --yes --package netlify-cli --registry=https://registry.npmjs.org --cache .\.npm-cache netlify deploy --build --prod
```

部署完成后，把 Netlify 生产域名填回 Render 的 `CORS_ALLOWED_ORIGINS`，然后重新部署后端。

最终 Render 环境变量应类似：

```text
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=gomoku-django-backend.onrender.com
CORS_ALLOWED_ORIGINS=https://你的项目.netlify.app
```

如果你绑定了自定义域名，`DJANGO_ALLOWED_HOSTS` 和 `CORS_ALLOWED_ORIGINS` 也要追加自定义域名，多个值用英文逗号分隔。

## 5. 线上验收

1. 打开前端网址。
2. 游客状态只能进入单机。
3. 注册两个账号。
4. 账号 A 创建房间。
5. 账号 B 加入房间。
6. 测试聊天、换位、落子同步。
7. 测试有禁手房间中黑棋长连、双四、双三会被拒绝。
8. 两个账号都离开房间后，回到房间列表确认该房间消失。

## 6. 常见问题

- 前端能打开但登录失败：检查 `VITE_API_BASE_URL` 是否以 `/api` 结尾。
- 房间能进入但聊天/落子不同步：检查 `VITE_WS_BASE_URL` 是否以 `/ws` 结尾，并且使用 `wss://`。
- 后端报 CORS：把 Netlify 正式域名加入 Render 的 `CORS_ALLOWED_ORIGINS`，不要漏掉 `https://`。
- 后端 400 Bad Request：把 Render 后端域名加入 `DJANGO_ALLOWED_HOSTS`。
- 本地 PowerShell 安装前端依赖失败：使用 `npm.cmd`，不要直接用 `npm`。
- Netlify CLI 在 PowerShell 里失败：使用 `npx.cmd`，不要直接用 `npx`；并显式指定 `--registry=https://registry.npmjs.org`，避免旧淘宝源证书过期。
