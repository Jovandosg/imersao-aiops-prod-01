---
adr_number: "001"
status: aceito
created: 2026-10-18
supersedes: ""
superseded_by: ""
---

# ADR 001: Exposição via Service LoadBalancer, sem Ingress

## Contexto

O kube-news roda num único ambiente cloud na DigitalOcean (DOKS), didático e descartável, que precisa ser acessível pela internet. O manifesto precisa ser agnóstico de provedor ([ADR 004](004-manifesto-kubernetes-agnostico.md)) e simples o bastante para servir de material didático.

Fatos verificados em 2026-10-18:
- O DOKS provisiona um Load Balancer da DigitalOcean a partir de um `Service type: LoadBalancer`. Ajustes como tamanho e certificado TLS são feitos por annotations específicas da DO ([DO docs](https://docs.digitalocean.com/products/kubernetes/how-to/add-load-balancers/index.html.md)).
- O ingress-nginx da comunidade foi aposentado em março/2026, sem releases nem patches de segurança. A recomendação oficial é migrar para a Gateway API ([kubernetes.io](https://kubernetes.io/blog/2025/11/11/ingress-Nginx-retirement/)).

## Alternativas Consideradas

- **`Service type: LoadBalancer`** — o mais simples e agnóstico: funciona em qualquer cloud com cloud controller. Contra: TLS no LB exige annotation do provedor, e cada Service exposto vira um LB.
- **Gateway API + controller + cert-manager** — o padrão atual, agnóstico, com TLS no cluster. Contra: mais peças para instalar e operar; só se justifica com domínio + TLS.
- **Ingress** — API antiga. O controller mais comum (ingress-nginx) foi aposentado; exigiria outro controller.

## Decisão

A aplicação é exposta por **`Service type: LoadBalancer`, em HTTP, sem Ingress**. A decisão é do usuário ("o acesso será via loadbalancer"; "não quero o uso de ingress"). Pesou a simplicidade didática e a compatibilidade com o manifesto agnóstico.

O banco nunca é exposto por LoadBalancer: fica só em `ClusterIP` *(premissa — confirme ou corrija)*.

## Consequências

- **Positivas:** um único objeto expõe a app. Nenhum componente extra no cluster. O manifesto roda igual em qualquer cluster com suporte a LoadBalancer.
- **Negativas:** sem TLS. O tráfego é HTTP puro, porque TLS no LB da DO exigiria annotation e quebraria o ADR 004 *(premissa — confirme ou corrija)*. Sem roteamento por host ou path.
- **Neutras / trade-offs aceitos:** em clusters sem cloud controller (ex.: kind local), o Service fica com `EXTERNAL-IP` em `pending` e precisa de outro meio de acesso (port-forward ou um provedor de LB local). A validação local usa o `nodePort` fixo do Service, mapeado pelo kind — ver [ADR 009](009-validacao-local-kind-nodeport.md).
