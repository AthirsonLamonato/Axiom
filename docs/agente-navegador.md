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

## Planos supervisionados

O dashboard expõe uma fila local para revisar e executar planos compostos. Um plano possui entre uma e trinta etapas e cada etapa contém o nome de uma ferramenta, seus argumentos e, opcionalmente, um texto esperado para verificação.

Para criar um plano por API local:

```bash
curl -X POST http://127.0.0.1:7755/api/tasks/plan \
  -H "Content-Type: application/json" \
  -H "X-CSRF-Token: TOKEN_DA_SESSAO" \
  -d '{"steps":[{"tool":"browser_start","args":{"url":"https://example.com"}},{"tool":"browser_inspect","args":{"max_chars":2000}}]}'
```

O plano aparece no painel **Planos de tarefas** do dashboard com os estados `pending`, `running`, `completed`, `failed` ou `rejected`. A execução só começa quando você clica em **Aprovar e executar**. A rejeição encerra o plano sem chamar nenhuma ferramenta.

A aprovação do dashboard é a confirmação explícita das ações sensíveis que estejam dentro daquele plano. Mesmo assim, o agente para a sequência quando uma ferramenta falha ou quando a verificação definida para uma etapa não é satisfeita.

## Modo supervisionado do loop agentivo

Para fazer com que pedidos complexos sejam apenas planejados e nunca executados diretamente pelo loop agentivo, ative:

```yaml
agent:
  require_plan_approval: true
```

Quando o modelo selecionar ferramentas, o Paçoca criará um plano `pending` na fila local e responderá com o identificador do plano. Nenhuma ferramenta será executada nesse momento. Abra o dashboard, revise as etapas e clique em **Aprovar e executar** ou **Rejeitar**.

Com `require_plan_approval: false`, o comportamento anterior permanece: o loop executa as ferramentas diretamente, respeitando as confirmações individuais já existentes. Para um agente pessoal que opere sites e formulários, o modo supervisionado é o recomendado.
