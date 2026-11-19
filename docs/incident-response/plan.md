# Plano de Ação: Incidentes de Dados Pessoais (SCRUM-101 e SCRUM-102)

Atualizado em 17/11/2026. O roteiro executável para demonstrar este plano está em [demo.md](demo.md).

Todo vazamento ou acesso indevido a dados pessoais no Índice é registrado no sistema, tratado por um administrador em etapas fixas, comunicado à ANPD e aos titulares dentro do prazo da LGPD, e coberto por backups criptografados que nunca trazem de volta quem pediu exclusão.

## Papéis

O tratamento é dos administradores do sistema (perfil ADMIN), que são os encarregados de segurança da aplicação. Os demais perfis não acessam o registro.

| Papel | Quem | O que faz |
| --- | --- | --- |
| Quem detecta | Qualquer pessoa da equipe ou do cliente | Avisa um administrador assim que perceber vazamento, acesso indevido ou perda de dados |
| Quem registra | Administrador | Abre o incidente no sistema; fica gravado como `reported_by` |
| Responsável pelo tratamento | Administrador nomeado no incidente (`assigned_to`) | Conduz contenção, análise, comunicações e encerramento |
| Contato dos titulares | Endereço do encarregado configurado no ambiente (`INCIDENT_CONTACT_EMAIL`) | Aparece no e-mail enviado aos afetados para dúvidas e direitos LGPD |
| Infraestrutura | Responsável pelo servidor | Cron dos backups e guarda da chave de criptografia |
| Governança | Product owner | Confirmou classificação, prazos e a ausência de tela no frontend |

Não há tela no frontend: o registro é operado pela API e consultado no admin do Django em modo somente leitura. Toda leitura e toda escrita ficam na trilha de auditoria.

## Fluxo de tratamento

O incidente passa por cinco etapas fixas, sempre nesta ordem, com duas voltas permitidas: da análise para a contenção e da resolução para a análise. Qualquer outro salto é recusado pelo sistema.

1. **Registro (REPORTED).** O administrador abre o incidente com título, descrição, tipo, severidade, quando ocorreu e quando foi detectado, categorias de dados, quantidade de titulares e os usuários e documentos envolvidos. O sistema gera a referência `INC-<ano>-<sequencial>` e calcula o prazo da ANPD na hora.
2. **Contenção (CONTAINMENT).** Cada medida vira uma ação registrada: tipo (contenção, erradicação, recuperação, comunicação ou outra), descrição, quem executou e quando. Um incidente simples pode ir do registro direto para a análise.
3. **Análise (ANALYSIS).** Causa raiz registrada no incidente. Se a contenção se mostrar insuficiente, volta para a etapa 2.
4. **Resolução (RESOLVED).** Medidas concluídas. Se algo reabrir, volta para a análise e a data de resolução é limpa.
5. **Encerramento (CLOSED).** Só é aceito com pelo menos uma ação registrada, os titulares comunicados e a ANPD comunicada quando exigido. Encerrado, o incidente fica congelado: nada mais pode ser alterado.

Cada mudança de etapa entra num histórico que o banco impede de editar ou apagar, com autor e observação opcional. A listagem mostra os incidentes por etapa, severidade, tipo e os com prazo da ANPD vencido.

## Classificação

As listas abaixo foram confirmadas pela product owner e são as únicas aceitas pelo sistema. A severidade define se a ANPD precisa ser comunicada: de MEDIUM para cima, sim, por padrão.

| Dimensão | Valores |
| --- | --- |
| Tipo de incidente | Acesso não autorizado · Divulgação indevida · Perda ou destruição de dados · Exposição de credenciais · Envio ao destinatário errado · Software malicioso · Outro |
| Severidade | LOW · MEDIUM · HIGH · CRITICAL |
| Categorias de dados pessoais | Identificação (nome, e-mail) · Credenciais · Dados profissionais (cargo, área) · Histórico de acesso e auditoria · Conteúdo de documentos técnicos · Outra |
| Tipos de ação | Contenção · Erradicação · Recuperação · Comunicação · Outra |

Um incidente pode listar várias categorias de dados. A severidade e a exigência de comunicar a ANPD podem ser revistas pelo administrador durante o tratamento; o prazo é recalculado.

## Prazos e comunicações

A ANPD é comunicada em até 3 dias úteis a partir da detecção (Resolução CD/ANPD 15/2024), e os titulares são comunicados por e-mail pelo próprio sistema antes do encerramento.

| Comunicação | Quando é exigida | Prazo | Como é feita e registrada |
| --- | --- | --- | --- |
| ANPD | Severidade MEDIUM, HIGH ou CRITICAL (padrão; o administrador pode ligar ou desligar) | 3 dias úteis após a detecção; a listagem marca os vencidos | Feita fora do sistema, pelo canal da ANPD; o administrador registra a data no incidente |
| Titulares afetados | Sempre, antes do encerramento | Assim que a contenção permitir informar o que aconteceu | E-mail oficial enviado pelo sistema (SCRUM-102) ou comunicação externa registrada com a data |

O e-mail aos titulares (SCRUM-102) vai para os usuários listados como afetados no incidente, decisão da product owner: quem está ligado aos documentos afetados (responsável, quem cadastrou, autores de revisão, quem pediu acesso) só é comunicado se o administrador o incluir na lista. O administrador vê a lista e a prévia exata da mensagem antes de enviar. A mensagem traz o que aconteceu, quais dados, as medidas já tomadas, se a ANPD foi comunicada, orientações por categoria de dado (troca de senha, atenção a golpes) e o contato do encarregado; descrição interna e causa raiz nunca saem.

Cada envio fica registrado por pessoa com status, tentativas, data e o nome do erro quando falha. Falha de um destinatário não para os outros; uma rotina no servidor reenvia só o que falhou, até três tentativas. Quando todos recebem, o incidente é marcado como comunicado aos titulares, o que libera o encerramento.

## Backups

Os dois bancos têm snapshots criptografados gerados por um cron no servidor: PostgreSQL a cada 4 horas guardado por 7 dias, MongoDB uma vez por dia guardado por 30 dias.

| Item | Decisão |
| --- | --- |
| O que é exportado | PostgreSQL como fixtures do Django (restaurável com `loaddata`); MongoDB como Extended JSON de cada coleção (restaurável com `mongoimport`) |
| Criptografia | AES-256-GCM com chave de 64 caracteres hexadecimais no ambiente (aprovado pela equipe); arquivo comprimido antes de cifrar |
| Frequência e retenção | PostgreSQL 4h/7 dias (42 arquivos), MongoDB 24h/30 dias (30 arquivos); os mais antigos são apagados e o histórico marca a poda |
| Registro | Cada execução fica na tabela de backups com status, arquivo, tamanho, SHA-256 e quantidade de registros; consultável por administradores |
| Agendamento | Crontab no servidor que hospeda os containers (linhas prontas no README) |
| Custódia da chave | Gerenciador de senhas da equipe, com o responsável pela infraestrutura como dono; o deploy copia a chave para o `.env` do servidor e para nenhum outro lugar |
| Rotação da chave | Nova chave no gerenciador e no `.env`, reinicia a api; a chave anterior fica guardada até o último arquivo dela ser podado, e arquivos antigos abrem passando a chave anterior ao comando |
| Destino externo | Fica para um card separado (VM compartilhada ou storage); hoje os arquivos ficam no próprio servidor |

A chave que protege o registro de exclusões (HMAC dos e-mails, `EXCLUDED_IDENTIFIER_HMAC_KEY`) segue a mesma regra de custódia: sem ela, o registro não pode ser conferido.

## Restauração

Um snapshot nunca volta ao uso sem a reaplicação das exclusões LGPD: quem pediu exclusão da conta, ou foi anonimizado ao ser desligado, ainda existe com nome, e-mail e senha em todo snapshot anterior a esse momento.

1. Descriptografar o snapshot com a chave do período (arquivo antigo usa a chave anterior).
2. Carregar os dados: PostgreSQL com `loaddata` em banco vazio, MongoDB com `mongoimport` por coleção.
3. Reaplicar as exclusões com o comando `reapply_user_erasures`, apontando o snapshot mais recente para trazer o registro de exclusões atualizado.

O registro de exclusões guarda, para cada pessoa excluída, o HMAC do e-mail, o tipo de exclusão (anonimizada ou apagada) e a data. Ele já bloqueia novos cadastros com esses e-mails; agora também é a memória de quem não pode voltar. O comando compara todos os usuários restaurados com o registro e repete a anonimização ou a exclusão pelos mesmos serviços usados na época, repassando o trabalho da pessoa a outro gestor e gravando uma entrada de auditoria por usuário. Quem não tiver gestor substituto é listado no final para tratamento manual.

Os arquivos de backup retêm os dados excluídos até a poda (7 e 30 dias); por isso a retenção é curta e o passo 3 é obrigatório.

## Pendências e próximos passos

O plano está implementado e os dois PRs estão verdes no CI, aguardando review. Fica em aberto o destino externo dos backups e dois pontos de infraestrutura.

- [ ] Review e merge do PR #66 (SCRUM-101: registro de incidentes, backups, restauração com reaplicação das exclusões)
- [ ] Review e merge do PR #70 (SCRUM-102: e-mail aos titulares), depois do #66
- [ ] Criar o card do destino externo dos backups (VM compartilhada ou storage)
- [ ] Infraestrutura: habilitar TLS no PostgreSQL da VM compartilhada (hoje a conexão vai sem criptografia)
- [ ] Combinar que a VM compartilhada só recebe migrations a partir da `develop`
- [ ] Mesclar os PRs #66 e #70 antes de congelar o schema na VM
- [ ] Guardar a chave de criptografia dos backups e a chave do registro de exclusões no gerenciador de senhas da equipe
- [ ] Produção: credenciais SMTP do cliente para o envio real dos e-mails (hoje o padrão escreve as mensagens no log)
