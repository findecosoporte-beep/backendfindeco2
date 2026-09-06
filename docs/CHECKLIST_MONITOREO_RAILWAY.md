# Checklist de monitoreo — FINDECO en Railway

Usa esta lista cuando falle el **login**, aparezca **CORS** o salga **502**.

## URLs rápidas

| Qué | URL |
|-----|-----|
| API (health) | https://web-production-93580.up.railway.app/api/v1/health/ |
| Front | https://frontend-production-c94e1.up.railway.app |
| Proyecto Railway | diligent-sparkle → servicios `web`, `frontend`, `MySQL` |

## CLI útil

```bash
cd backendfindeco2
railway status
railway deployment list --limit 5
railway logs
railway logs --build
```

---

## 1. ¿La API está viva?

- [ ] Abrir `/api/v1/health/` → debe responder `200` y `{"status":"ok"}`
- [ ] Si no responde o da **502**: la API está caída o reiniciando
- [ ] En Railway → servicio **web** → **Deployments**: ¿último deploy SUCCESS?
- [ ] En **Logs** del deploy activo: ¿Gunicorn escuchando? ¿errores de migrate/MySQL?

**Si hay 502:** espera 1–2 min (reinicio) y reintenta. Si persiste, revisa logs de runtime.

---

## 2. ¿Es CORS de verdad o un 502 disfrazado?

Chrome a veces muestra *“blocked by CORS”* cuando la API devolvió **502** sin headers CORS.

- [ ] En DevTools → **Network** → request fallido: mira el **status** real (502 vs 401 vs 0)
- [ ] Si es **502**: no es CORS; vuelve al paso 1
- [ ] Si es **200/401** pero sin `Access-Control-Allow-Origin`: sí es CORS
- [ ] En Railway → **web** → Variables: `CORS_ALLOWED_ORIGINS` debe incluir  
  `https://frontend-production-c94e1.up.railway.app`

Comprobar headers (PowerShell):

```powershell
Invoke-WebRequest `
  -Uri "https://web-production-93580.up.railway.app/api/v1/health/" `
  -Headers @{ Origin = "https://frontend-production-c94e1.up.railway.app" } `
  -UseBasicParsing
# Debe verse: Access-Control-Allow-Origin = https://frontend-production-c94e1.up.railway.app
```

---

## 3. Fallo de login (token /me)

Orden típico del front: `POST /api/v1/token/` → `GET /api/v1/me/`

- [ ] **Network** → `token/`: ¿200? ¿credenciales incorrectas (401)?
- [ ] Si `token/` es 200 y `me/` falla: mira status de `me/` (401 = token/sesión; 502 = API)
- [ ] Logs API: busca `POST /api/v1/token/` y `GET /api/v1/me/` con el mismo timestamp
- [ ] Front → Variable `VITE_API_BASE_URL` =  
  `https://web-production-93580.up.railway.app/api/v1`  
  (sin typo, sin guión extra al final del path)

---

## 4. Build / deploy fallido

- [ ] Railway → **web** → deploy FALLIDO → pestaña **Build**
- [ ] Si sale `pipefail` / `Illegal option` en `scripts/build.sh`: revisar finales de línea **LF** (no CRLF)
- [ ] Confirmar que `.gitattributes` tiene `*.sh text eol=lf`
- [ ] Redeploy: desde la carpeta de la API → `railway up --detach`

---

## 5. Base de datos

- [ ] Servicio **MySQL** en Railway → estado **Online**
- [ ] Logs de **web** al arrancar: `migrate` OK (sin errores de conexión)
- [ ] Variables en **web**: `MYSQLHOST`, `MYSQLPORT`, `MYSQLUSER`, `MYSQLPASSWORD`, `MYSQLDATABASE` referenciadas al MySQL

---

## 6. Front no refleja cambios

- [ ] Deploy del servicio **frontend** en SUCCESS
- [ ] Hard refresh (Ctrl+F5) o ventana privada
- [ ] `VITE_*` solo aplica en **build**: si cambiaste la variable, hay que **redeploy** el front

---

## Orden recomendado en una incidencia

1. Health de la API  
2. Último deploy `web` (SUCCESS / FAILED)  
3. Logs runtime (últimos 2–5 min)  
4. Network del navegador (status real del request)  
5. Variables CORS / `VITE_API_BASE_URL`  
6. MySQL Online + migrate en logs  

---

## Señales rápidas

| Síntoma | Causa más probable |
|---------|-------------------|
| CORS + `net::ERR_FAILED 502` | API caída / reiniciando |
| Login 401 en `token/` | Usuario/contraseña o usuario inactivo |
| `token/` 200 y `me/` 401 | Token no enviado o inválido |
| Health 200 pero front viejo | Cache o front sin redeploy |
| Build falla en `build.sh` | Scripts con CRLF o comando de build |
