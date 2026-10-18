# NodeNotReady Warning no kube-controller-manager
- **Severidade:** MEDIO
- **Namespace:** kube-system
- **Recursos Afetados:** kube-controller-manager-kind-control-plane
- **Eventos:** 857e012d-4e25-4125-bf6f-e6c173f654e8
- **Conclusao:** inconclusiva

### Causa Raiz
Evento isolado com mensagem "Node is not ready" foi capturado no kube-controller-manager, com timestamp 19:44:56. Entretanto, o pod describe mostra Status=Running, Ready=True, ContainersReady=True e todos os health checks passando. O nó (kind-control-plane) está em status Ready. Este evento pode ter sido temporário durante o bootstrap inicial do cluster (timestamp mostra ~8 segundos após criação) ou pode ser um evento fantasma já resolvido.

### Evidencias
- Timestamp do evento: 19:44:56 (primeiro evento depois da criação do cluster)
- Pod status atual: Running, Ready=True, ContainersReady=True
- Nó status: Ready
- Não há erros nos logs do pod (container iniciou com sucesso)
- Probe startup/liveness/readiness: todas passando
- Nenhum evento mais recente de NodeNotReady

### Solucao Recomendada
Monitorar eventos subsequentes do kube-controller-manager. Se NodeNotReady persistir ou recorrer, investigar a saúde do nó (CPU, memory, disk space, network connectivity). Verificar logs do kubelet no nó para identificar problemas de inicialização. Para este evento específico e isolado, nenhuma ação é necessária no momento, pois é histórico e o sistema está funcionando normalmente.

### Comando Sugerido
```bash
kubectl get events -n kube-system --field-selector involvedObject.name=kube-controller-manager-kind-control-plane --sort-by='.lastTimestamp'
kubectl logs -n kube-system kube-controller-manager-kind-control-plane --tail=50
```