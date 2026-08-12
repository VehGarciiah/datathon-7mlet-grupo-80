# CRM Web

Frontend Angular 22 do simulador de CRM do Grupo 101. A interface usa Fluent 2 e consome
somente a API Java pelo caminho relativo `/api`.

## Desenvolvimento local

Com a API Java disponível em `http://127.0.0.1:8081`:

```powershell
npm install
npm start
```

Acesse <http://127.0.0.1:4200>. O proxy de desenvolvimento encaminha `/api` para o backend.

## Qualidade

```powershell
npm run build
npm run test:e2e
npm audit --omit=dev
```

Os testes Playwright cobrem integração de leitura com a API, fluxo de recomendação e
feedback, axe/WCAG 2.2 AA, temas claro e escuro, teclado, reduced motion, forced colors,
RTL e reflow entre 320 e 1440 pixels.

Para testar o container já publicado na porta 80:

```powershell
$env:E2E_BASE_URL='http://127.0.0.1'
npm run test:e2e
Remove-Item Env:E2E_BASE_URL
```

## Container

Na raiz do repositório:

```powershell
podman compose up -d --build crm-web
```
