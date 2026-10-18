---
adr_number: "008"
status: aceito
created: 2026-10-18
supersedes: ""
superseded_by: ""
---

# ADR 008: Rotas de simulação de falha ativas e públicas

## Contexto

A aplicação tem rotas para simular falhas: `PUT /unhealth` deixa a instância "não saudável" (todas as requisições passam a responder 500) e `PUT /unreadyfor/:seconds` faz `/ready` falhar por um tempo. Elas existem para demonstrar liveness e readiness no Kubernetes. Com a exposição por LoadBalancer ([ADR 001](001-exposicao-via-service-loadbalancer.md)), ficam acessíveis pela internet.

## Alternativas Consideradas

- **Ativas e públicas** — a demonstração ao vivo funciona contra o ambiente cloud. Contra: qualquer pessoa derruba a app com um `PUT`.
- **Ativas só no dev, desligadas por env var no cluster** — elimina o risco público. Contra: a demonstração de probes no cluster cloud deixa de existir.
- **Protegidas (token ou acesso só interno)** — mantém a demonstração com menos exposição. Contra: exige autenticação ou outro caminho de acesso, contrariando a simplicidade.

## Decisão

As rotas de simulação de falha ficam **ativas e expostas publicamente** no ambiente cloud. Decisão do usuário: "ficam ativas e expostas".

## Consequências

- **Positivas:** dá para demonstrar ao vivo o pod saindo do Service (readiness) e sendo reiniciado (liveness).
- **Negativas:** qualquer pessoa com o IP do LoadBalancer pode tornar instâncias não saudáveis ou não prontas e degradar o ambiente.
- **Neutras / trade-offs aceitos:** aceitável só porque o ambiente é didático e descartável. Com 2 réplicas, a liveness reinicia as instâncias afetadas e o ambiente se recupera sozinho. Se surgir um ambiente com usuários reais, este ADR deve ser substituído.
