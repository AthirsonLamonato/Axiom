# Agente de navegador do Paçoca

O Paçoca agora possui uma camada opcional de automação local e supervisionada de navegador. Ela é desativada por padrão e usa um perfil separado para não compartilhar automaticamente todas as sessões do seu navegador principal.

## Instalação

No ambiente Python do Paçoca, instale a dependência opcional e o navegador Chromium:

```bash
pip install playwright
python -m playwright install chromium
```

## Configuração

Edite `core/config.yaml`:

```yaml
browser:
  enabled: true
  headless: false
  allow_all_domains: true
  profile_dir: data/browser-profile
  allowed_domains: []
```

Com `allow_all_domains: true`, o agente pode navegar em qualquer domínio usando URLs `http` ou `https`. Para restringir o acesso, use `allow_all_domains: false` e preencha `allowed_domains`; nesse modo, subdomínios dos domínios listados são permitidos. Esquemas como `file://` não são aceitos.

Para usar uma conta pessoal, abra o navegador do agente e faça o login manualmente. Com o modo amplo ativado, ele poderá navegar em qualquer domínio HTTP ou HTTPS; o perfil fica em `data/browser-profile`.

## Ferramentas disponíveis

| Ferramenta | Função | Risco padrão |
|---|---|---|
| `browser_start` | Inicia a sessão persistente | Baixo |
| `browser_navigate` | Abre uma URL autorizada | Baixo |
| `browser_inspect` | Lê título, URL e texto visível | Baixo |
| `browser_click` | Clica usando seletor CSS | Médio |
| `browser_fill` | Preenche um campo | Médio |
| `browser_screenshot` | Salva uma captura da página | Baixo |
| `browser_close` | Encerra a sessão | Baixo |

As ferramentas já estão disponíveis para o loop agentivo do Paçoca. O módulo `modules/task_agent.py` também permite executar uma sequência de etapas com parada automática quando uma etapa falha ou não passa na verificação configurada.

## Segurança

O modo amplo também permite alcançar páginas de bancos, serviços financeiros e contas administrativas, portanto não reutilize o perfil principal do seu navegador sem entender esse risco. Ações de envio, exclusão, compra, publicação e alterações irreversíveis devem continuar exigindo confirmação explícita. A configuração não concede ao navegador permissão para executar comandos do sistema.

O modo sem custo recomendado é executar o modelo e o navegador localmente no seu próprio computador. O navegador deve ser instalado manualmente apenas uma vez e o computador precisa permanecer ligado enquanto uma tarefa estiver sendo executada.
